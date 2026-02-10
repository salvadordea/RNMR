"""Background worker for RNMR GUI operations."""
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, Signal, QThread

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from renamer.parser import parse_filename, is_media_file
from renamer.tmdb import TMDBClient, TMDBError
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


class ScanWorker(QObject):
    """Worker for scanning files and building rename plan."""

    # Signals
    started = Signal()
    progress = Signal(int, int)  # current, total
    item_found = Signal(int, object)  # row index, RenameItem
    log = Signal(str)
    finished = Signal()
    error = Signal(str)

    def __init__(
        self,
        folder_path: str,
        recursive: bool,
        use_tmdb: bool,
        include_episode_title: bool,
        series_template: str | None = None,
        movie_template: str | None = None
    ):
        super().__init__()
        self.folder_path = Path(folder_path)
        self.recursive = recursive
        self.use_tmdb = use_tmdb
        self.include_episode_title = include_episode_title
        self.series_template = series_template
        self.movie_template = movie_template
        self._cancelled = False

    def cancel(self):
        """Cancel the operation."""
        self._cancelled = True

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

            # Setup TMDB client if needed
            tmdb_client = None
            if self.use_tmdb:
                try:
                    cache = Cache(self.folder_path)
                    tmdb_client = TMDBClient(cache=cache, verbose=False)
                    self.log.emit("TMDB client initialized (en-US)")
                except TMDBError as e:
                    self.log.emit(f"[WARN] TMDB unavailable: {e}")

            # Process each file
            for i, filepath in enumerate(files):
                if self._cancelled:
                    self.log.emit("Scan cancelled.")
                    break

                self.progress.emit(i + 1, len(files))

                try:
                    item = self._process_file(filepath, tmdb_client)
                    self.item_found.emit(i, item)
                except Exception as e:
                    # Create error item
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

    def _process_file(
        self,
        filepath: Path,
        tmdb_client: TMDBClient | None
    ) -> RenameItem:
        """Process a single file and return rename item."""
        parsed = parse_filename(filepath)
        extension = filepath.suffix

        new_filename = None
        metadata = {
            "title_guess": parsed.title_guess,
            "media_type": parsed.media_type,
            "season": parsed.season,
            "episodes": parsed.episodes,
            "year": parsed.year,
        }

        # Try TMDB lookup
        if tmdb_client:
            try:
                if parsed.media_type == "series":
                    series = tmdb_client.search_series(parsed.title_guess)
                    if series and parsed.season is not None:
                        metadata["tmdb_id"] = series.id
                        metadata["tmdb_title"] = series.original_name or series.name

                        episode_details = []
                        if self.include_episode_title and len(parsed.episodes) == 1:
                            for ep_num in parsed.episodes:
                                ep = tmdb_client.get_episode_details(
                                    series.id, parsed.season, ep_num
                                )
                                if ep:
                                    episode_details.append(ep)
                                    metadata["episode_title"] = ep.name

                        # Use template if provided, otherwise use default formatting
                        if self.series_template:
                            new_filename = format_series_with_template(
                                series,
                                parsed.season,
                                parsed.episodes,
                                episode_details if episode_details else None,
                                extension,
                                self.series_template
                            )
                        else:
                            new_filename = format_series_name(
                                series,
                                parsed.season,
                                parsed.episodes,
                                episode_details if episode_details else None,
                                extension,
                                self.include_episode_title
                            )
                else:
                    movie = tmdb_client.search_movie(parsed.title_guess, parsed.year)
                    if movie:
                        metadata["tmdb_id"] = movie.id
                        metadata["tmdb_title"] = movie.original_title or movie.title
                        # Use template if provided
                        if self.movie_template:
                            new_filename = format_movie_with_template(
                                movie, extension, self.movie_template
                            )
                        else:
                            new_filename = format_movie_name(movie, extension, keep_year=True)

            except Exception as e:
                self.log.emit(f"[WARN] TMDB error for {filepath.name}: {e}")

        # Fallback if TMDB didn't work
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
