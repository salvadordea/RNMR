"""Cache module for storing TMDB lookups locally."""
import json
from pathlib import Path
from typing import Any


CACHE_FILE = ".renamer_cache.json"


class Cache:
    """Local JSON cache for TMDB lookups."""

    def __init__(self, cache_dir: Path | None = None):
        """
        Initialize the cache.

        Args:
            cache_dir: Directory to store cache file. Defaults to current directory.
        """
        if cache_dir is None:
            cache_dir = Path.cwd()
        self.cache_path = cache_dir / CACHE_FILE
        self._cache: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        """Load cache from disk."""
        if self.cache_path.exists():
            try:
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return self._empty_cache()
        return self._empty_cache()

    def _empty_cache(self) -> dict[str, Any]:
        """Return empty cache structure."""
        return {
            "title_to_id": {},
            "movie_searches": {},
            "series_searches": {},
            "episodes": {},
        }

    def _save(self) -> None:
        """Save cache to disk."""
        try:
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, indent=2, ensure_ascii=False)
        except IOError:
            pass  # Silently fail if we can't write cache

    def _normalize_key(self, key: str) -> str:
        """Normalize a string for use as cache key."""
        return key.lower().strip()

    def get_title_id(self, title: str, media_type: str) -> int | None:
        """
        Get cached TMDB ID for a title.

        Args:
            title: The title to look up
            media_type: 'movie' or 'series'

        Returns:
            TMDB ID if cached, None otherwise
        """
        key = f"{media_type}:{self._normalize_key(title)}"
        return self._cache["title_to_id"].get(key)

    def set_title_id(self, title: str, media_type: str, tmdb_id: int) -> None:
        """
        Cache a TMDB ID for a title.

        Args:
            title: The title
            media_type: 'movie' or 'series'
            tmdb_id: The TMDB ID
        """
        key = f"{media_type}:{self._normalize_key(title)}"
        self._cache["title_to_id"][key] = tmdb_id
        self._save()

    def get_movie_search(self, title: str, year: int | None = None) -> dict | None:
        """
        Get cached movie search result.

        Args:
            title: The search title
            year: Optional year filter

        Returns:
            Cached movie data if found, None otherwise
        """
        key = f"{self._normalize_key(title)}:{year or ''}"
        return self._cache["movie_searches"].get(key)

    def set_movie_search(self, title: str, year: int | None, result: dict) -> None:
        """
        Cache a movie search result.

        Args:
            title: The search title
            year: Optional year filter
            result: The movie data to cache
        """
        key = f"{self._normalize_key(title)}:{year or ''}"
        self._cache["movie_searches"][key] = result
        self._save()

    def get_series_search(self, title: str) -> dict | None:
        """
        Get cached series search result.

        Args:
            title: The search title

        Returns:
            Cached series data if found, None otherwise
        """
        key = self._normalize_key(title)
        return self._cache["series_searches"].get(key)

    def set_series_search(self, title: str, result: dict) -> None:
        """
        Cache a series search result.

        Args:
            title: The search title
            result: The series data to cache
        """
        key = self._normalize_key(title)
        self._cache["series_searches"][key] = result
        self._save()

    def get_episode(self, series_id: int, season: int, episode: int) -> dict | None:
        """
        Get cached episode details.

        Args:
            series_id: TMDB series ID
            season: Season number
            episode: Episode number

        Returns:
            Cached episode data if found, None otherwise
        """
        key = f"{series_id}:s{season}e{episode}"
        return self._cache["episodes"].get(key)

    def set_episode(self, series_id: int, season: int, episode: int, result: dict) -> None:
        """
        Cache episode details.

        Args:
            series_id: TMDB series ID
            season: Season number
            episode: Episode number
            result: The episode data to cache
        """
        key = f"{series_id}:s{season}e{episode}"
        self._cache["episodes"][key] = result
        self._save()

    def clear(self) -> None:
        """Clear all cached data."""
        self._cache = self._empty_cache()
        self._save()
