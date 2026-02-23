"""Background worker for RNMR GUI operations."""
import hashlib
import re
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, Signal, QThread, QMutex, QWaitCondition

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from renamer.parser import parse_filename, is_media_file
from renamer.tmdb import TMDBClient, TMDBError
from renamer.models import TMDBSeries, TMDBMovie, TMDBEpisode
from renamer.formatter import (
    format_series_name,
    format_series_with_template,
    format_movie_name,
    format_movie_with_template,
    format_fallback,
    get_new_path,
    filenames_match
)
from renamer.cache import Cache
from renamer.id_mapping import IDMapping
from renamer.detection import (
    DetectionController, DetectionState, Action, BatchContext,
)

# Sentinel that means "no result provided yet" -- distinct from None
# which means "user chose to skip".
_NO_RESULT = object()


@dataclass
class RenameItem:
    """Represents a file to be renamed."""
    original_path: Path
    new_path: Path | None
    new_name: str
    status: str  # "pending", "renamed", "skipped", "error"
    error_message: str | None = None
    checked: bool = True
    metadata: dict | None = None


@dataclass
class ScanContext:
    """Scan-wide settings, created once at the start of each scan.

    Lives entirely on the worker thread.  The main thread communicates
    state changes (e.g. *skip_all_unresolved*) through the existing
    ``set_lookup_result`` mechanism using sentinel values.
    """
    metadata_language: str = "en-US"
    skip_all_unresolved: bool = False


class ScanWorker(QObject):
    """Worker for scanning files and building rename plan.

    Architecture (strict phase separation):

      Phase 1 -- Parse every filename (no network).
      Phase 2 -- resolve_batch_identity(): group by title, ONE TMDB
                 lookup per group, ONE interactive prompt per group,
                 pre-fetch ALL episode details.  Every TMDB call and
                 every dialog lives here.
      Phase 3 -- Format each file using the pre-resolved BatchContext.
                 Zero TMDB calls.  Zero dialogs.
    """

    # Signals
    started = Signal()
    progress = Signal(int, int)  # current, total
    item_found = Signal(int, object)  # row index, RenameItem
    log = Signal(str)
    status_update = Signal(str)  # non-blocking status bar message
    finished = Signal()
    error = Signal(str)
    lookup_failed = Signal(dict)  # emitted once per group when TMDB returns nothing
    tmdb_select_requested = Signal(dict)  # emitted when always_confirm_tmdb is ON
    type_select_requested = Signal(dict)  # emitted when always_ask_media_type is ON

    def __init__(
        self,
        folder_path: str,
        recursive: bool,
        use_tmdb: bool,
        include_episode_title: bool,
        series_template: str | None = None,
        movie_template: str | None = None,
        interactive: bool = False,
        api_key: str | None = None,
        metadata_language: str = "en-US",
        episode_title_language: str = "same",
        force_english_episode_titles: bool = False,
        always_confirm_tmdb: bool = False,
        always_ask_media_type: bool = False,
    ):
        super().__init__()
        self.folder_path = Path(folder_path)
        self.recursive = recursive
        self.use_tmdb = use_tmdb
        self.include_episode_title = include_episode_title
        self.series_template = series_template
        self.movie_template = movie_template
        self._interactive = interactive
        self._api_key = api_key
        self._metadata_language = metadata_language
        self._episode_title_language = episode_title_language
        self._force_english_episode_titles = force_english_episode_titles
        self._always_confirm_tmdb = always_confirm_tmdb
        self._always_ask_media_type = always_ask_media_type
        self._cancelled = False

        # Cross-thread synchronization for interactive lookups
        self._lookup_mutex = QMutex()
        self._lookup_condition = QWaitCondition()
        self._lookup_result = _NO_RESULT  # set by main thread

        # Set during Phase 2 for episode prefetch
        self._current_tmdb_client: TMDBClient | None = None

    def cancel(self):
        """Cancel the operation."""
        self._cancelled = True
        # Wake the wait condition in case we're blocked on a lookup dialog
        self._lookup_condition.wakeAll()

    def set_lookup_result(self, result):
        """Called from main thread to provide the user's selection."""
        self._lookup_mutex.lock()
        self._lookup_result = result
        self._lookup_condition.wakeAll()
        self._lookup_mutex.unlock()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self):
        """Execute the scan operation."""
        try:
            self.started.emit()
            self.log.emit(f"Scanning: {self.folder_path}")

            # Find media files
            files = self._find_media_files()
            if not files:
                self.log.emit("No media files found.")
                self.finished.emit()
                return

            self.log.emit(f"Found {len(files)} media file(s)")

            # Build scan context (fixed for the entire scan)
            scan_context = ScanContext(
                metadata_language=self._metadata_language,
            )

            # Setup TMDB client if needed
            tmdb_client = None
            if self.use_tmdb:
                try:
                    cache = Cache(self.folder_path)
                    tmdb_client = TMDBClient(
                        api_key=self._api_key, cache=cache, verbose=False,
                        language=scan_context.metadata_language,
                    )
                    self.log.emit(
                        f"TMDB client initialized ({scan_context.metadata_language})"
                    )
                except TMDBError as e:
                    self.log.emit(f"[WARN] TMDB unavailable: {e}")

            # Phase 1 -- Parse every file (no network)
            parsed_files = []
            for filepath in files:
                parsed = parse_filename(filepath)
                parsed_files.append((filepath, parsed))

            # Phase 2 -- Batch identification (ALL TMDB work happens here)
            batch_contexts = self._resolve_batch_identity(
                parsed_files, tmdb_client, IDMapping(self.folder_path),
                scan_context,
            )
            # tmdb_client is NOT passed to Phase 3.

            # Phase 3 -- Format each file (no TMDB, no dialogs)
            for i, (filepath, parsed) in enumerate(parsed_files):
                if self._cancelled:
                    self.log.emit("Scan cancelled.")
                    break

                self.progress.emit(i + 1, len(parsed_files))

                group_key = self._group_key(parsed.raw_name)
                ctx = batch_contexts.get(group_key)

                try:
                    item = self._format_file(filepath, parsed, ctx)
                    self.item_found.emit(i, item)
                except Exception as e:
                    item = RenameItem(
                        original_path=filepath,
                        new_path=None,
                        new_name="",
                        status="error",
                        error_message=str(e)
                    )
                    self.item_found.emit(i, item)
                    self.log.emit(f"[ERROR] {filepath.name}: {e}")

            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))

    # ------------------------------------------------------------------
    # File discovery
    # ------------------------------------------------------------------

    def _find_media_files(self) -> list[Path]:
        """Find all media files in the folder."""
        files = []

        if self.folder_path.is_file():
            if is_media_file(self.folder_path):
                return [self.folder_path]
            return []

        if not self.folder_path.is_dir():
            return []

        if self.recursive:
            for item in self.folder_path.rglob("*"):
                if item.is_file() and is_media_file(item):
                    files.append(item)
        else:
            for item in self.folder_path.iterdir():
                if item.is_file() and is_media_file(item):
                    files.append(item)

        return sorted(files)

    # ------------------------------------------------------------------
    # Title normalisation and grouping
    # ------------------------------------------------------------------

    # Episode-pattern anchors (same patterns the parser uses)
    _EP_ANCHOR = re.compile(
        r'[sS]\d{1,2}[eE]\d{1,2}'
        r'|\b\d{1,2}x\d{1,2}\b'
        r'|[sS]eason\s*\d{1,2}\s*[eE]pisode\s*\d{1,2}'
    )

    @staticmethod
    def _group_key(raw_name: str) -> str:
        """Derive a grouping key from the raw filename stem.

        Takes only the text BEFORE the episode pattern so that episode
        titles (which vary per file) are excluded.  Falls back to the
        full normalised stem for movies (no episode pattern).
        """
        # Normalise separators (dots / underscores -> spaces)
        name = re.sub(r'[._]', ' ', raw_name)
        name = re.sub(r'--+', ' ', name)

        m = ScanWorker._EP_ANCHOR.search(name)
        if m:
            name = name[:m.start()]

        # Strip symbols, collapse whitespace, lowercase
        name = re.sub(r'[^\w\s]', ' ', name.lower())
        return re.sub(r'\s+', ' ', name).strip()

    @staticmethod
    def _group_by_title(
        parsed_files: list[tuple[Path, Any]]
    ) -> dict[str, list[tuple[Path, Any]]]:
        """Group files by their normalized parsed title."""
        groups: dict[str, list[tuple[Path, Any]]] = {}
        for filepath, parsed in parsed_files:
            key = ScanWorker._group_key(parsed.raw_name)
            groups.setdefault(key, []).append((filepath, parsed))
        return groups

    # ------------------------------------------------------------------
    # Phase 2 -- Batch identity resolution (ALL TMDB + ALL dialogs)
    # ------------------------------------------------------------------

    def _resolve_batch_identity(
        self,
        parsed_files: list[tuple[Path, Any]],
        tmdb_client: TMDBClient | None,
        id_mapping: IDMapping,
        scan_context: ScanContext,
    ) -> dict[str, BatchContext]:
        """Resolve TMDB identity for every title group.

        This is the ONLY place in the entire scan where TMDB calls and
        interactive dialogs are allowed.  After this function returns,
        no further network or UI work is needed.

        Returns a dict mapping normalised title -> BatchContext.
        """
        groups = self._group_by_title(parsed_files)
        batch_contexts: dict[str, BatchContext] = {}

        for group_key, entries in groups.items():
            self.log.emit(
                f"[BATCH] Group '{group_key}': {len(entries)} file(s)"
            )

        # Build controller once per scan
        self._current_tmdb_client = tmdb_client
        controller = None
        if tmdb_client:
            controller = DetectionController(
                tmdb_client=tmdb_client,
                id_mapping=id_mapping,
                settings={
                    "always_ask_media_type": self._always_ask_media_type,
                    "always_confirm_tmdb": self._always_confirm_tmdb,
                    "interactive_fallback": self._interactive,
                },
                log_fn=lambda msg: self.log.emit(msg),
            )

        for group_key, group_entries in groups.items():
            if self._cancelled:
                break

            ctx = self._resolve_group(
                group_key, group_entries, controller, scan_context,
            )
            batch_contexts[group_key] = ctx

        self.log.emit("[BATCH] Identification executed once")
        return batch_contexts

    def _resolve_group(
        self,
        group_key: str,
        group_entries: list[tuple[Path, Any]],
        controller: DetectionController | None,
        scan_context: ScanContext,
    ) -> BatchContext:
        """Resolve ONE title group using the DetectionController state machine."""
        if not controller:
            return BatchContext(metadata_language=scan_context.metadata_language)

        batch = controller.create_batch(
            group_key, group_entries, scan_context.metadata_language,
        )

        try:
            while True:
                if self._cancelled:
                    controller.skip(batch)
                    break

                action = controller.step(batch)

                if action == Action.DONE:
                    break
                elif action == Action.CONTINUE:
                    continue
                elif action == Action.NEED_MEDIA_TYPE:
                    if scan_context.skip_all_unresolved:
                        controller.skip(batch)
                        continue
                    self.type_select_requested.emit(batch.signal_info())
                    result = self._wait_for_response()
                    if result is None:
                        controller.skip(batch)
                    elif result.get("__skip_all__"):
                        scan_context.skip_all_unresolved = True
                        controller.skip(batch)
                    else:
                        controller.set_media_type(batch, result["media_type"])
                elif action == Action.NEED_SELECTION:
                    if scan_context.skip_all_unresolved:
                        controller.skip(batch)
                        continue
                    self.tmdb_select_requested.emit(batch.signal_info())
                    result = self._wait_for_response()
                    if result is None:
                        controller.skip(batch)
                    elif result.get("__skip_all__"):
                        scan_context.skip_all_unresolved = True
                        controller.skip(batch)
                    else:
                        controller.set_selection(batch, result)
                elif action == Action.NEED_FALLBACK:
                    if scan_context.skip_all_unresolved:
                        controller.skip(batch)
                        continue
                    self.lookup_failed.emit(batch.signal_info())
                    result = self._wait_for_response()
                    if result is None:
                        controller.skip(batch)
                    elif result.get("__skip_all__"):
                        scan_context.skip_all_unresolved = True
                        controller.skip(batch)
                    else:
                        controller.set_fallback_result(batch, result)

            # Metadata source finalization
            if batch.found and batch.metadata_source not in ("ffprobe", "tmdb"):
                batch.metadata_source = "tmdb"
            elif not batch.found and not batch.skipped:
                batch.metadata_source = "unidentified"

            # Episode prefetch (after CONFIRMED only)
            if (
                batch.state == DetectionState.CONFIRMED
                and batch.series
                and self.include_episode_title
            ):
                ctx = batch.to_batch_context()
                self._prefetch_episodes(
                    ctx, group_entries, self._current_tmdb_client,
                )
                batch.episode_cache = ctx.episode_cache

        except Exception as e:
            self.log.emit(f"[WARN] TMDB error for group '{group_key}': {e}")

        return batch.to_batch_context()

    # ------------------------------------------------------------------
    # Episode prefetch helpers
    # ------------------------------------------------------------------

    def _resolve_episode_language(self, ctx: BatchContext) -> str | None:
        """Determine the language to use for episode title requests.

        Returns a language tag to pass to ``get_episode_details``, or
        *None* to use the client's default (metadata_language).
        """
        if self._force_english_episode_titles:
            return "en-US"

        mode = self._episode_title_language
        if mode == "en":
            return "en-US"
        if mode == "original" and ctx.series and ctx.series.original_language:
            return ctx.series.original_language
        # "same" or fallback -- use the client default
        return None

    def _prefetch_episodes(
        self,
        ctx: BatchContext,
        group_entries: list[tuple[Path, Any]],
        tmdb_client: TMDBClient
    ):
        """Pre-fetch all episode details needed by this group.

        Populates ctx.episode_cache so _format_file never touches TMDB.
        Only fetches for single-episode files (multi-episode files
        don't include episode titles).
        """
        ep_language = self._resolve_episode_language(ctx)

        pairs: set[tuple[int, int]] = set()
        for _, parsed in group_entries:
            if parsed.season is not None and len(parsed.episodes) == 1:
                for ep in parsed.episodes:
                    pairs.add((parsed.season, ep))

        for season, ep_num in sorted(pairs):
            if self._cancelled:
                break
            try:
                ep = tmdb_client.get_episode_details(
                    ctx.series.id, season, ep_num,
                    language=ep_language,
                )
                if ep:
                    ctx.episode_cache[(season, ep_num)] = ep
            except Exception:
                pass  # episode detail is nice-to-have

    # ------------------------------------------------------------------
    # Unified interactive wait
    # ------------------------------------------------------------------

    def _wait_for_response(self):
        """Block until the main thread provides a result via set_lookup_result()."""
        self._lookup_mutex.lock()
        self._lookup_result = _NO_RESULT
        self._lookup_mutex.unlock()

        self._lookup_mutex.lock()
        while self._lookup_result is _NO_RESULT and not self._cancelled:
            self._lookup_condition.wait(self._lookup_mutex)
        result = self._lookup_result
        self._lookup_result = _NO_RESULT
        self._lookup_mutex.unlock()

        if self._cancelled or result is None:
            return None
        return result

    # ------------------------------------------------------------------
    # Phase 3 -- Per-file formatting (no TMDB, no dialogs)
    # ------------------------------------------------------------------

    def _format_file(
        self,
        filepath: Path,
        parsed,
        ctx: BatchContext | None,
    ) -> RenameItem:
        """Build a RenameItem for a single file.

        Uses ONLY the pre-resolved BatchContext.  No network calls.
        No dialogs.  No tmdb_client parameter.
        """
        extension = filepath.suffix
        new_filename = None
        metadata = {
            "title_guess": parsed.title_guess,
            "media_type": parsed.media_type,
            "season": parsed.season,
            "episodes": parsed.episodes,
            "year": parsed.year,
        }

        if ctx and ctx.mapped:
            metadata["mapped_id"] = True
        metadata["metadata_source"] = ctx.metadata_source if ctx else "inferred"

        # -- Skipped batch (user explicitly skipped) --
        if ctx and ctx.skipped:
            return RenameItem(
                original_path=filepath,
                new_path=None,
                new_name="",
                status="skipped",
                error_message="Skipped by user",
                checked=False,
                metadata=metadata,
            )

        # -- Series --
        if ctx and ctx.series and parsed.season is not None:
            metadata["tmdb_id"] = ctx.series.id
            metadata["tmdb_title"] = ctx.series.original_name or ctx.series.name

            # Look up pre-fetched episode details from the cache
            episode_details = []
            if self.include_episode_title and len(parsed.episodes) == 1:
                for ep_num in parsed.episodes:
                    ep = ctx.episode_cache.get((parsed.season, ep_num))
                    if ep:
                        episode_details.append(ep)
                        metadata["episode_title"] = ep.name

            if self.series_template:
                new_filename = format_series_with_template(
                    ctx.series, parsed.season, parsed.episodes,
                    episode_details if episode_details else None,
                    extension, self.series_template
                )
            else:
                new_filename = format_series_name(
                    ctx.series, parsed.season, parsed.episodes,
                    episode_details if episode_details else None,
                    extension, self.include_episode_title
                )

        # -- Movie --
        elif ctx and ctx.movie:
            metadata["tmdb_id"] = ctx.movie.id
            metadata["tmdb_title"] = ctx.movie.original_title or ctx.movie.title
            if self.movie_template:
                new_filename = format_movie_with_template(
                    ctx.movie, extension, self.movie_template
                )
            else:
                new_filename = format_movie_name(
                    ctx.movie, extension, keep_year=True
                )

        # -- Fallback --
        if not new_filename:
            new_filename = format_fallback(parsed, extension)

        new_path = get_new_path(filepath, new_filename)

        # Check if already named correctly
        if filenames_match(filepath.name, new_filename):
            return RenameItem(
                original_path=filepath,
                new_path=new_path,
                new_name=new_filename,
                status="skipped",
                error_message="Already named correctly",
                checked=False,
                metadata=metadata
            )

        # Check if destination exists
        if new_path.exists() and filepath.resolve() != new_path.resolve():
            return RenameItem(
                original_path=filepath,
                new_path=new_path,
                new_name=new_filename,
                status="error",
                error_message="Destination already exists",
                checked=False,
                metadata=metadata
            )

        return RenameItem(
            original_path=filepath,
            new_path=new_path,
            new_name=new_filename,
            status="pending",
            metadata=metadata
        )


class RenameWorker(QObject):
    """Worker for executing file renames."""

    # Signals
    started = Signal()
    progress = Signal(int, int)  # current, total
    item_updated = Signal(int, str, str)  # row, status, error
    log = Signal(str)
    finished = Signal(int, int, int)  # renamed, skipped, errors
    error = Signal(str)

    def __init__(self, items: list[tuple[int, RenameItem]]):
        """
        Args:
            items: List of (row_index, RenameItem) tuples to rename
        """
        super().__init__()
        self.items = items
        self._cancelled = False

    def cancel(self):
        """Cancel the operation."""
        self._cancelled = True

    def run(self):
        """Execute the rename operation."""
        try:
            self.started.emit()

            renamed = 0
            skipped = 0
            errors = 0

            total = len(self.items)

            for i, (row, item) in enumerate(self.items):
                if self._cancelled:
                    self.log.emit("Rename cancelled.")
                    break

                self.progress.emit(i + 1, total)

                if item.status != "pending" or not item.new_path:
                    skipped += 1
                    continue

                try:
                    # Perform rename
                    item.original_path.rename(item.new_path)
                    renamed += 1
                    self.item_updated.emit(row, "renamed", "")
                    self.log.emit(f"Renamed: {item.original_path.name}")

                except Exception as e:
                    errors += 1
                    self.item_updated.emit(row, "error", str(e))
                    self.log.emit(f"[ERROR] {item.original_path.name}: {e}")

            self.finished.emit(renamed, skipped, errors)

        except Exception as e:
            self.error.emit(str(e))


@dataclass
class DuplicateItem:
    """Represents a duplicate file result."""
    path: Path
    size: int
    mtime: float
    hash: str
    norm_name: str
    group_type: str  # "hash" or "name"


class DuplicateScanWorker(QObject):
    """Worker for scanning and identifying duplicate files."""

    started = Signal()
    progress = Signal(int, int)  # current, total
    status_update = Signal(str)
    log = Signal(str)
    finished = Signal(object)  # list of groups
    error = Signal(str)

    _TAG_PATTERNS = [
        r'\b(2160p|1080p|720p|480p|4k|8k)\b',
        r'\b(x264|x265|h264|h265|hevc|av1|avc|xvid|divx)\b',
        r'\b(bluray|brrip|web[- ]?dl|webrip|hdrip|dvdrip|remux|uhd|hdtv)\b',
        r'\b(aac|ac3|dts|ddp|truehd|atmos|flac|mp3)\b',
        r'\b(repack|proper|rerip|extended|internal|limited|uncut)\b',
        r'\b(dolby|hdr|dv|sdr|hdr10|hdr10\+|hlg)\b',
        r'\b(web|dl|rip|cam|ts|tc|telesync|dvdscr|screener)\b',
        r'\b(dual\s*audio|multi|subs?|dubbed)\b',
        r'\b(10bit|12bit|8bit|hi10p)\b',
        r'\b(dolby\s*vision|vision|dovi)\b',
        r'\b(uncensored|remastered|collector\'s|special\s*edition)\b',
        r'\b(rarbg|yify|yts|evo|ntb|fg|snahp|vxt|ctrlhd)\b',
    ]

    def __init__(self, folder_path: str, recursive: bool, include_all_files: bool = False):
        super().__init__()
        self.folder_path = Path(folder_path)
        self.recursive = recursive
        self.include_all_files = include_all_files
        self._cancelled = False

    def cancel(self):
        """Cancel the operation."""
        self._cancelled = True

    def run(self):
        """Execute duplicate scan operation."""
        try:
            self.started.emit()
            self.status_update.emit("Scanning files...")

            files = self._find_media_files()
            if not files:
                self.log.emit("No media files found.")
                self.finished.emit([])
                return

            total_files = len(files)
            file_infos = []
            for i, path in enumerate(files, start=1):
                if self._cancelled:
                    self.log.emit("Duplicate scan cancelled.")
                    self.finished.emit([])
                    return

                self.progress.emit(i, total_files)
                try:
                    stat = path.stat()
                    norm_name = self._normalize_name(path.name)
                    file_infos.append({
                        "path": path,
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                        "norm_name": norm_name,
                    })
                except Exception as e:
                    self.log.emit(f"[WARN] Skipping {path.name}: {e}")

            if self._cancelled:
                self.log.emit("Duplicate scan cancelled.")
                self.finished.emit([])
                return

            # Exact duplicates via hash
            self.status_update.emit("Computing quick hashes...")
            exact_groups, full_hashes = self._find_exact_duplicates(file_infos)

            if self._cancelled:
                self.log.emit("Duplicate scan cancelled.")
                self.finished.emit([])
                return

            # Name-normalized duplicates (excluding files already in exact groups)
            self.status_update.emit("Matching normalized filenames...")
            name_groups = self._find_name_duplicates(
                file_infos, exact_groups, full_hashes
            )

            groups = exact_groups + name_groups
            self.finished.emit(groups)

        except Exception as e:
            self.error.emit(str(e))

    # ------------------------------------------------------------------
    # File discovery
    # ------------------------------------------------------------------

    def _find_media_files(self) -> list[Path]:
        """Find media files (or all files when enabled) in the folder."""
        files = []

        if self.folder_path.is_file():
            if self.include_all_files or is_media_file(self.folder_path):
                return [self.folder_path]
            return []

        if not self.folder_path.is_dir():
            return []

        if self.recursive:
            for item in self.folder_path.rglob("*"):
                if item.is_file() and (self.include_all_files or is_media_file(item)):
                    files.append(item)
        else:
            for item in self.folder_path.iterdir():
                if item.is_file() and (self.include_all_files or is_media_file(item)):
                    files.append(item)

        return sorted(files)

    # ------------------------------------------------------------------
    # Normalization + hashing
    # ------------------------------------------------------------------

    def _normalize_name(self, filename: str) -> str:
        """Normalize filename by removing tags, codec, resolution, etc."""
        name = Path(filename).stem
        name = re.sub(r'[\[\(\{].*?[\]\)\}]', ' ', name)
        name = name.replace('.', ' ').replace('_', ' ').replace('-', ' ')
        for pattern in self._TAG_PATTERNS:
            name = re.sub(pattern, ' ', name, flags=re.IGNORECASE)
        name = re.sub(r'[^\w\s]', ' ', name.lower())
        name = re.sub(r'\s+', ' ', name).strip()
        return name

    @staticmethod
    def _md5_full(path: Path, chunk_size: int = 1024 * 1024) -> str:
        """Compute full MD5 hash for a file."""
        h = hashlib.md5()
        with path.open("rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _md5_quick(path: Path, chunk_size: int = 1024 * 1024) -> str:
        """Compute a quick MD5 hash using first + last chunk plus size."""
        size = path.stat().st_size
        h = hashlib.md5()
        h.update(size.to_bytes(8, byteorder="little", signed=False))

        with path.open("rb") as f:
            if size <= chunk_size * 2:
                h.update(f.read())
            else:
                first = f.read(chunk_size)
                h.update(first)
                f.seek(-chunk_size, 2)
                last = f.read(chunk_size)
                h.update(last)
        return h.hexdigest()

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    def _find_exact_duplicates(self, file_infos: list[dict]) -> tuple[list, dict]:
        """Find exact duplicates using quick hash + full hash verification."""
        size_groups: dict[int, list[dict]] = {}
        for info in file_infos:
            size_groups.setdefault(info["size"], []).append(info)

        quick_candidates = [g for g in size_groups.values() if len(g) > 1]
        total_quick = sum(len(g) for g in quick_candidates)
        processed = 0

        quick_groups: dict[tuple[int, str], list[dict]] = {}
        for group in quick_candidates:
            for info in group:
                if self._cancelled:
                    return [], {}
                try:
                    quick = self._md5_quick(info["path"])
                    key = (info["size"], quick)
                    quick_groups.setdefault(key, []).append(info)
                except Exception as e:
                    self.log.emit(f"[WARN] Hash failed {info['path'].name}: {e}")
                processed += 1
                if total_quick:
                    self.progress.emit(processed, total_quick)

        full_hashes: dict[Path, str] = {}
        exact_groups = []

        full_candidates = [g for g in quick_groups.values() if len(g) > 1]
        total_full = sum(len(g) for g in full_candidates)
        processed = 0

        for group in full_candidates:
            if self._cancelled:
                return [], {}

            full_map: dict[str, list[dict]] = {}
            for info in group:
                if self._cancelled:
                    return [], {}
                try:
                    full_hash = self._md5_full(info["path"])
                    full_hashes[info["path"]] = full_hash
                    full_map.setdefault(full_hash, []).append(info)
                except Exception as e:
                    self.log.emit(f"[WARN] Full hash failed {info['path'].name}: {e}")
                processed += 1
                if total_full:
                    self.progress.emit(processed, total_full)

            for h, items in full_map.items():
                if len(items) > 1:
                    group_items = []
                    for info in items:
                        group_items.append(DuplicateItem(
                            path=info["path"],
                            size=info["size"],
                            mtime=info["mtime"],
                            hash=full_hashes.get(info["path"], h),
                            norm_name=info["norm_name"],
                            group_type="hash",
                        ))
                    exact_groups.append({
                        "group_type": "hash",
                        "items": group_items,
                    })

        return exact_groups, full_hashes

    def _find_name_duplicates(
        self,
        file_infos: list[dict],
        exact_groups: list[dict],
        full_hashes: dict[Path, str],
    ) -> list[dict]:
        """Find duplicates by normalized name, excluding exact dupes."""
        exact_paths = {
            item.path
            for group in exact_groups
            for item in group["items"]
        }

        name_groups: dict[str, list[dict]] = {}
        for info in file_infos:
            if not info["norm_name"]:
                continue
            if info["path"] in exact_paths:
                continue
            name_groups.setdefault(info["norm_name"], []).append(info)

        groups = []
        candidates = [g for g in name_groups.values() if len(g) > 1]
        total_full = sum(len(g) for g in candidates)
        processed = 0

        for group in candidates:
            if self._cancelled:
                return []
            group_items = []
            for info in group:
                if self._cancelled:
                    return []
                try:
                    if info["path"] not in full_hashes:
                        full_hashes[info["path"]] = self._md5_full(info["path"])
                except Exception as e:
                    self.log.emit(f"[WARN] Full hash failed {info['path'].name}: {e}")
                    full_hashes.setdefault(info["path"], "")
                processed += 1
                if total_full:
                    self.progress.emit(processed, total_full)

                group_items.append(DuplicateItem(
                    path=info["path"],
                    size=info["size"],
                    mtime=info["mtime"],
                    hash=full_hashes.get(info["path"], ""),
                    norm_name=info["norm_name"],
                    group_type="name",
                ))
            groups.append({
                "group_type": "name",
                "items": group_items,
            })

        return groups
