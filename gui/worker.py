"""Background worker for RNMR GUI operations."""
import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QObject, Signal, QThread, QMutex, QWaitCondition

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from renamer.parser import parse_filename, is_media_file
from renamer.cleaner import clean_for_search
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

# Minimum match confidence (0.0-1.0) below which the interactive
# fallback dialog is shown, even when TMDB returned results.
CONFIDENCE_THRESHOLD = 0.6

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


@dataclass
class BatchContext:
    """Resolved TMDB metadata shared by all files with the same parsed title.

    Contains everything needed to format filenames.  No further TMDB
    calls are required once this object is built.
    """
    series: TMDBSeries | None = None
    movie: TMDBMovie | None = None
    media_type: str | None = None
    mapped: bool = False
    skipped: bool = False
    metadata_source: str = "inferred"  # "tmdb" | "inferred"
    metadata_language: str = "en-US"
    # Pre-fetched episode details keyed by (season, episode_number)
    episode_cache: dict[tuple[int, int], TMDBEpisode] = field(default_factory=dict)


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
    finished = Signal()
    error = Signal(str)
    lookup_failed = Signal(dict)  # emitted once per group when TMDB returns nothing

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
        metadata_language: str = "en-US"
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
        self._cancelled = False

        # Cross-thread synchronization for interactive lookups
        self._lookup_mutex = QMutex()
        self._lookup_condition = QWaitCondition()
        self._lookup_result = _NO_RESULT  # set by main thread

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
    # TMDB fetch helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_series(tmdb_client: TMDBClient, tmdb_id: int) -> TMDBSeries | None:
        data = tmdb_client._request(f"/tv/{tmdb_id}")
        if not data:
            return None
        first_air_date = data.get("first_air_date", "")
        return TMDBSeries(
            id=data["id"],
            name=data.get("name", ""),
            original_name=data.get("original_name", ""),
            first_air_year=int(first_air_date[:4]) if first_air_date else None,
            overview=data.get("overview", ""),
        )

    @staticmethod
    def _fetch_movie(tmdb_client: TMDBClient, tmdb_id: int) -> TMDBMovie | None:
        data = tmdb_client._request(f"/movie/{tmdb_id}")
        if not data:
            return None
        release_date = data.get("release_date", "")
        return TMDBMovie(
            id=data["id"],
            title=data.get("title", ""),
            original_title=data.get("original_title", ""),
            year=int(release_date[:4]) if release_date else None,
            overview=data.get("overview", ""),
        )

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

        for group_key, group_entries in groups.items():
            if self._cancelled:
                break

            ctx = self._resolve_group(
                group_key, group_entries, tmdb_client, id_mapping,
                scan_context,
            )
            batch_contexts[group_key] = ctx

        self.log.emit("[BATCH] Identification executed once")
        return batch_contexts

    def _resolve_group(
        self,
        group_key: str,
        group_entries: list[tuple[Path, Any]],
        tmdb_client: TMDBClient | None,
        id_mapping: IDMapping,
        scan_context: ScanContext,
    ) -> BatchContext:
        """Resolve ONE title group.

        Steps:
          1. Check mapped IDs
          2. Automatic TMDB search (one call)
          3. Interactive fallback dialog (once) -- skipped when
             *scan_context.skip_all_unresolved* is set
          4. Pre-fetch all episode details for every (season, episode)
             pair in the group
        """
        ctx = BatchContext(metadata_language=scan_context.metadata_language)
        if not tmdb_client:
            return ctx

        first_filepath, first_parsed = group_entries[0]
        ctx.media_type = first_parsed.media_type

        # -- Step 1: Check whether any file already has a mapped ID --
        mapped_id = None
        mapped_type = None
        for filepath, _parsed in group_entries:
            mid, mtype = id_mapping.get_id(filepath.name)
            if mid and mtype:
                mapped_id = mid
                mapped_type = mtype
                break

        try:
            if mapped_id and mapped_type:
                # ---------- Mapped-ID path (no search needed) ----------
                self.log.emit(
                    f"Using mapped ID for '{group_key}': "
                    f"{mapped_type}:{mapped_id}"
                )
                ctx.mapped = True
                ctx.media_type = mapped_type
                if mapped_type == "series":
                    ctx.series = self._fetch_series(tmdb_client, mapped_id)
                else:
                    ctx.movie = self._fetch_movie(tmdb_client, mapped_id)
            else:
                # -- Step 2: Automatic search with aggressive cleaning --
                is_series = first_parsed.media_type == "series"

                if is_series:
                    # For series the parser already stripped the episode
                    # pattern from title_guess, so clean that.
                    clean_title, _ = clean_for_search(
                        first_parsed.title_guess, is_series=True
                    )
                    search_title = clean_title or first_parsed.title_guess
                    self.log.emit(
                        f"[CLEAN] Series search: '{search_title}'"
                    )
                    ctx.series = tmdb_client.search_series(search_title)
                    # Retry with parser title if cleaner gave different text
                    if (not ctx.series
                            and search_title != first_parsed.title_guess):
                        self.log.emit(
                            f"[CLEAN] Retry with parser title: "
                            f"'{first_parsed.title_guess}'"
                        )
                        ctx.series = tmdb_client.search_series(
                            first_parsed.title_guess
                        )
                else:
                    # For movies, use raw_name so the cleaner can
                    # truncate at the year boundary.
                    clean_title, clean_year = clean_for_search(
                        first_parsed.raw_name, is_series=False
                    )
                    search_title = clean_title or first_parsed.title_guess
                    search_year = (
                        clean_year
                        if clean_year is not None
                        else first_parsed.year
                    )
                    self.log.emit(
                        f"[CLEAN] Movie search: '{search_title}'"
                        + (f" year={search_year}" if search_year else "")
                    )
                    ctx.movie = tmdb_client.search_movie(
                        search_title, search_year
                    )
                    # Retry with parser title if cleaner gave different text
                    if (not ctx.movie
                            and search_title != first_parsed.title_guess):
                        self.log.emit(
                            f"[CLEAN] Retry with parser title: "
                            f"'{first_parsed.title_guess}'"
                        )
                        ctx.movie = tmdb_client.search_movie(
                            first_parsed.title_guess, first_parsed.year
                        )

                # -- Step 3: Interactive fallback (once per group) --
                # Trigger when there are no results OR confidence is low.
                found = ctx.series or ctx.movie
                confidence = found.confidence if found else 0.0
                if found:
                    self.log.emit(
                        f"[MATCH] '{group_key}' -> confidence={confidence:.2f}"
                    )

                needs_fallback = (
                    not found or confidence < CONFIDENCE_THRESHOLD
                )
                if needs_fallback and self._interactive:
                    if scan_context.skip_all_unresolved:
                        # User previously chose "Skip All"
                        ctx.skipped = True
                        self.log.emit(
                            f"[SKIP] Auto-skipping '{group_key}' "
                            f"({len(group_entries)} file(s)) -- "
                            f"skip-all active"
                        )
                    else:
                        user_result = self._wait_for_user_input(
                            first_filepath, first_parsed, group_entries
                        )
                        if (user_result
                                and user_result.get("__skip_all__")):
                            scan_context.skip_all_unresolved = True
                            ctx.skipped = True
                            self.log.emit(
                                f"[SKIP] Skipping '{group_key}' "
                                f"({len(group_entries)} file(s)) -- "
                                f"skip-all activated by user"
                            )
                        elif user_result:
                            tmdb_id = user_result.get("tmdb_id")
                            media_type = user_result.get("media_type")
                            title = user_result.get("title")
                            if tmdb_id and media_type:
                                # Save mapping so future scans skip
                                # the dialog
                                id_mapping.set_id(
                                    first_filepath.name, tmdb_id,
                                    media_type, title
                                )
                                self.log.emit(
                                    f"Saved mapping for '{group_key}': "
                                    f"{media_type}:{tmdb_id}"
                                )
                                ctx.mapped = True
                                ctx.media_type = media_type
                                if media_type == "series":
                                    ctx.series = self._fetch_series(
                                        tmdb_client, tmdb_id
                                    )
                                else:
                                    ctx.movie = self._fetch_movie(
                                        tmdb_client, tmdb_id
                                    )
                        else:
                            # Single-batch skip (None result)
                            ctx.skipped = True
                            self.log.emit(
                                f"[SKIP] Skipping '{group_key}' "
                                f"({len(group_entries)} file(s)) -- "
                                f"user skipped"
                            )

            # Determine metadata source from resolution outcome
            if ctx.series or ctx.movie:
                ctx.metadata_source = "tmdb"

            # -- Step 4: Pre-fetch episode details for the whole group --
            if ctx.series and self.include_episode_title:
                self._prefetch_episodes(ctx, group_entries, tmdb_client)

        except Exception as e:
            self.log.emit(f"[WARN] TMDB error for group '{group_key}': {e}")

        return ctx

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
                    ctx.series.id, season, ep_num
                )
                if ep:
                    ctx.episode_cache[(season, ep_num)] = ep
            except Exception:
                pass  # episode detail is nice-to-have

    # ------------------------------------------------------------------
    # Interactive prompt (pauses worker, wakes when main thread responds)
    # ------------------------------------------------------------------

    def _wait_for_user_input(self, filepath, parsed, group_entries):
        """Emit lookup_failed and block until the main thread responds."""
        # Collect all unique seasons from the group
        seasons = sorted({
            p.season for _, p in group_entries
            if p.season is not None
        })

        info = {
            "filepath": str(filepath),
            "parsed_title": parsed.title_guess,
            "media_type": parsed.media_type,
            "seasons": seasons,
            "year": parsed.year,
            "file_count": len(group_entries),
        }

        self._lookup_mutex.lock()
        self._lookup_result = _NO_RESULT
        self._lookup_mutex.unlock()

        self.lookup_failed.emit(info)

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
