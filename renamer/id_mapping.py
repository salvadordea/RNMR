"""ID mapping for manual TMDB disambiguation."""
import json
import re
from pathlib import Path
from typing import Any


MAPPING_FILE = ".rnmr_ids.json"


class IDMapping:
    """Manages manual TMDB ID mappings for disambiguation."""

    def __init__(self, mapping_dir: Path | None = None):
        """
        Initialize ID mapping.

        Args:
            mapping_dir: Directory to store mapping file. Defaults to cwd.
        """
        if mapping_dir is None:
            mapping_dir = Path.cwd()
        self.mapping_path = mapping_dir / MAPPING_FILE
        self._mappings: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        """Load mappings from disk."""
        if self.mapping_path.exists():
            try:
                with open(self.mapping_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def _save(self) -> bool:
        """Save mappings to disk."""
        try:
            with open(self.mapping_path, 'w', encoding='utf-8') as f:
                json.dump(self._mappings, f, indent=2, ensure_ascii=False)
            return True
        except IOError:
            return False

    def _normalize_key(self, filename: str) -> str:
        """Normalize filename for use as key."""
        # Remove extension and normalize
        name = Path(filename).stem
        # Lowercase and remove special chars
        name = re.sub(r'[^\w\s]', ' ', name.lower())
        name = re.sub(r'\s+', ' ', name).strip()
        return name

    def get_id(self, filename: str) -> tuple[int | None, str | None]:
        """
        Get TMDB ID for a filename.

        Args:
            filename: The filename to look up

        Returns:
            Tuple of (tmdb_id, media_type) or (None, None) if not mapped
        """
        key = self._normalize_key(filename)

        # Try exact match first
        if key in self._mappings:
            entry = self._mappings[key]
            return entry.get("tmdb_id"), entry.get("media_type")

        # Try partial matches
        for mapped_key, entry in self._mappings.items():
            if mapped_key in key or key in mapped_key:
                return entry.get("tmdb_id"), entry.get("media_type")

        return None, None

    def set_id(
        self,
        filename: str,
        tmdb_id: int,
        media_type: str,
        title: str | None = None
    ) -> bool:
        """
        Set TMDB ID for a filename.

        Args:
            filename: The filename to map
            tmdb_id: TMDB ID
            media_type: "series" or "movie"
            title: Optional title for reference

        Returns:
            True if saved successfully
        """
        key = self._normalize_key(filename)
        self._mappings[key] = {
            "tmdb_id": tmdb_id,
            "media_type": media_type,
            "title": title,
            "original_filename": filename,
        }
        return self._save()

    def remove_id(self, filename: str) -> bool:
        """
        Remove mapping for a filename.

        Args:
            filename: The filename to unmap

        Returns:
            True if removed and saved
        """
        key = self._normalize_key(filename)
        if key in self._mappings:
            del self._mappings[key]
            return self._save()
        return False

    def get_all(self) -> dict[str, dict[str, Any]]:
        """Get all mappings."""
        return self._mappings.copy()

    def clear(self) -> bool:
        """Clear all mappings."""
        self._mappings = {}
        return self._save()


def parse_tmdb_url(url: str) -> tuple[int | None, str | None]:
    """
    Parse TMDB URL to extract ID and type.

    Supports:
    - https://www.themoviedb.org/tv/12345
    - https://www.themoviedb.org/movie/12345
    - tv:12345
    - movie:12345
    - 12345 (assumes series if ambiguous)

    Returns:
        Tuple of (tmdb_id, media_type) or (None, None) if invalid
    """
    url = url.strip()

    # URL format
    tv_match = re.search(r'themoviedb\.org/tv/(\d+)', url)
    if tv_match:
        return int(tv_match.group(1)), "series"

    movie_match = re.search(r'themoviedb\.org/movie/(\d+)', url)
    if movie_match:
        return int(movie_match.group(1)), "movie"

    # Short format: tv:12345 or movie:12345
    short_match = re.match(r'(tv|series|movie):(\d+)', url, re.IGNORECASE)
    if short_match:
        media_type = "series" if short_match.group(1).lower() in ("tv", "series") else "movie"
        return int(short_match.group(2)), media_type

    # Just a number
    if url.isdigit():
        return int(url), None  # Type needs to be specified

    return None, None
