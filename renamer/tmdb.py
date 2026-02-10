"""TMDB API client module."""
import os
import time
from difflib import SequenceMatcher
from typing import Callable

import requests

from .models import TMDBMovie, TMDBSeries, TMDBEpisode
from .cache import Cache


TMDB_BASE_URL = "https://api.themoviedb.org/3"
DEFAULT_TIMEOUT = 10
RATE_LIMIT_DELAY = 0.25  # 250ms between requests to avoid rate limiting


def normalize_for_comparison(text: str) -> str:
    """Normalize a string for comparison."""
    import re
    # Lowercase
    text = text.lower()
    # Remove special characters
    text = re.sub(r'[^\w\s]', '', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def similarity_score(s1: str, s2: str) -> float:
    """Calculate similarity between two strings."""
    s1_norm = normalize_for_comparison(s1)
    s2_norm = normalize_for_comparison(s2)
    return SequenceMatcher(None, s1_norm, s2_norm).ratio()


class TMDBClient:
    """Client for TMDB API."""

    def __init__(
        self,
        api_key: str | None = None,
        cache: Cache | None = None,
        language: str = "es-MX",
        interactive_callback: Callable[[list[dict], str], int | None] | None = None
    ):
        """
        Initialize TMDB client.

        Args:
            api_key: TMDB API key. If not provided, reads from TMDB_API_KEY env var.
            cache: Cache instance for storing lookups.
            language: Language for results (default: Spanish Mexico).
            interactive_callback: Callback for interactive selection.
                                  Receives (results, title) and returns selected index or None.
        """
        self.api_key = api_key or os.environ.get("TMDB_API_KEY")
        if not self.api_key:
            raise ValueError(
                "TMDB API key required. Set TMDB_API_KEY environment variable "
                "or pass api_key parameter."
            )
        self.cache = cache or Cache()
        self.language = language
        self.interactive_callback = interactive_callback
        self._last_request_time = 0.0

    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    def _request(
        self,
        endpoint: str,
        params: dict | None = None,
        retries: int = 3
    ) -> dict | None:
        """
        Make a request to the TMDB API.

        Args:
            endpoint: API endpoint (e.g., '/search/movie')
            params: Query parameters
            retries: Number of retries on failure

        Returns:
            JSON response or None on error
        """
        self._rate_limit()

        url = f"{TMDB_BASE_URL}{endpoint}"
        all_params = {
            "api_key": self.api_key,
            "language": self.language,
            **(params or {})
        }

        for attempt in range(retries):
            try:
                response = requests.get(url, params=all_params, timeout=DEFAULT_TIMEOUT)

                if response.status_code == 429:  # Rate limited
                    retry_after = int(response.headers.get("Retry-After", 1))
                    time.sleep(retry_after)
                    continue

                response.raise_for_status()
                return response.json()

            except requests.exceptions.Timeout:
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
                return None
            except requests.exceptions.RequestException:
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
                return None

        return None

    def _choose_best_match(
        self,
        results: list[dict],
        title: str,
        year: int | None = None,
        is_movie: bool = True
    ) -> dict | None:
        """
        Choose the best match from search results.

        Args:
            results: List of search results
            title: The title we're searching for
            year: Optional year to match
            is_movie: Whether we're searching for movies

        Returns:
            Best matching result or None
        """
        if not results:
            return None

        # If interactive mode and callback is set
        if self.interactive_callback and len(results) > 1:
            selected = self.interactive_callback(results, title)
            if selected is not None and 0 <= selected < len(results):
                return results[selected]

        # Score each result
        scored = []
        for result in results:
            title_field = "title" if is_movie else "name"
            original_title_field = "original_title" if is_movie else "original_name"
            date_field = "release_date" if is_movie else "first_air_date"

            result_title = result.get(title_field, "")
            original_title = result.get(original_title_field, "")

            # Calculate title similarity (use best of localized and original)
            title_sim = max(
                similarity_score(title, result_title),
                similarity_score(title, original_title)
            )

            # Year bonus
            year_bonus = 0.0
            if year:
                result_date = result.get(date_field, "")
                if result_date and len(result_date) >= 4:
                    result_year = int(result_date[:4])
                    if result_year == year:
                        year_bonus = 0.2
                    elif abs(result_year - year) == 1:
                        year_bonus = 0.1

            # Popularity as tiebreaker
            popularity = result.get("popularity", 0) / 1000  # Normalize

            score = title_sim + year_bonus + (popularity * 0.05)
            scored.append((score, result))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1] if scored else None

    def search_movie(self, title: str, year: int | None = None) -> TMDBMovie | None:
        """
        Search for a movie on TMDB.

        Args:
            title: Movie title to search for
            year: Optional release year

        Returns:
            TMDBMovie if found, None otherwise
        """
        # Check cache first
        cached = self.cache.get_movie_search(title, year)
        if cached:
            return TMDBMovie(
                id=cached["id"],
                title=cached["title"],
                original_title=cached["original_title"],
                year=cached.get("year"),
                overview=cached.get("overview", "")
            )

        # Search TMDB
        params = {"query": title}
        if year:
            params["year"] = year

        data = self._request("/search/movie", params)
        if not data or not data.get("results"):
            return None

        # Choose best match
        best = self._choose_best_match(data["results"], title, year, is_movie=True)
        if not best:
            return None

        # Extract year from release date
        release_year = None
        if best.get("release_date") and len(best["release_date"]) >= 4:
            release_year = int(best["release_date"][:4])

        movie = TMDBMovie(
            id=best["id"],
            title=best.get("title", ""),
            original_title=best.get("original_title", ""),
            year=release_year,
            overview=best.get("overview", "")
        )

        # Cache result
        self.cache.set_movie_search(title, year, {
            "id": movie.id,
            "title": movie.title,
            "original_title": movie.original_title,
            "year": movie.year,
            "overview": movie.overview
        })
        self.cache.set_title_id(title, "movie", movie.id)

        return movie

    def search_series(self, title: str) -> TMDBSeries | None:
        """
        Search for a TV series on TMDB.

        Args:
            title: Series title to search for

        Returns:
            TMDBSeries if found, None otherwise
        """
        # Check cache first
        cached = self.cache.get_series_search(title)
        if cached:
            return TMDBSeries(
                id=cached["id"],
                name=cached["name"],
                original_name=cached["original_name"],
                first_air_year=cached.get("first_air_year"),
                overview=cached.get("overview", "")
            )

        # Search TMDB
        params = {"query": title}
        data = self._request("/search/tv", params)
        if not data or not data.get("results"):
            return None

        # Choose best match
        best = self._choose_best_match(data["results"], title, is_movie=False)
        if not best:
            return None

        # Extract year from first air date
        first_air_year = None
        if best.get("first_air_date") and len(best["first_air_date"]) >= 4:
            first_air_year = int(best["first_air_date"][:4])

        series = TMDBSeries(
            id=best["id"],
            name=best.get("name", ""),
            original_name=best.get("original_name", ""),
            first_air_year=first_air_year,
            overview=best.get("overview", "")
        )

        # Cache result
        self.cache.set_series_search(title, {
            "id": series.id,
            "name": series.name,
            "original_name": series.original_name,
            "first_air_year": series.first_air_year,
            "overview": series.overview
        })
        self.cache.set_title_id(title, "series", series.id)

        return series

    def get_episode_details(
        self,
        series_id: int,
        season: int,
        episode: int
    ) -> TMDBEpisode | None:
        """
        Get episode details from TMDB.

        Args:
            series_id: TMDB series ID
            season: Season number
            episode: Episode number

        Returns:
            TMDBEpisode if found, None otherwise
        """
        # Check cache first
        cached = self.cache.get_episode(series_id, season, episode)
        if cached:
            return TMDBEpisode(
                series_id=cached["series_id"],
                season_number=cached["season_number"],
                episode_number=cached["episode_number"],
                name=cached["name"],
                overview=cached.get("overview", "")
            )

        # Fetch from TMDB
        endpoint = f"/tv/{series_id}/season/{season}/episode/{episode}"
        data = self._request(endpoint)
        if not data:
            return None

        ep = TMDBEpisode(
            series_id=series_id,
            season_number=season,
            episode_number=episode,
            name=data.get("name", ""),
            overview=data.get("overview", "")
        )

        # Cache result
        self.cache.set_episode(series_id, season, episode, {
            "series_id": ep.series_id,
            "season_number": ep.season_number,
            "episode_number": ep.episode_number,
            "name": ep.name,
            "overview": ep.overview
        })

        return ep
