"""TMDB API client module."""
import os
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

import requests

from .models import TMDBMovie, TMDBSeries, TMDBEpisode
from .cache import Cache


TMDB_BASE_URL = "https://api.themoviedb.org/3"
DEFAULT_TIMEOUT = 10
RATE_LIMIT_DELAY = 0.25  # 250ms between requests to avoid rate limiting
DEFAULT_LANGUAGE = "en-US"  # Always use English for consistency


def load_api_key() -> str | None:
    """
    Load TMDB API key from environment or .env file.

    Priority:
    1. TMDB_API_KEY environment variable
    2. .env file in current directory
    3. .env file in user home directory

    Returns:
        API key string or None if not found
    """
    # First check environment variable
    api_key = os.environ.get("TMDB_API_KEY")
    if api_key:
        return api_key

    # Try to load from .env files using python-dotenv if available
    try:
        from dotenv import load_dotenv

        # Try current directory first
        env_path = Path.cwd() / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            api_key = os.environ.get("TMDB_API_KEY")
            if api_key:
                return api_key

        # Try home directory
        home_env = Path.home() / ".env"
        if home_env.exists():
            load_dotenv(home_env)
            api_key = os.environ.get("TMDB_API_KEY")
            if api_key:
                return api_key

    except ImportError:
        # python-dotenv not installed, skip .env loading
        pass

    return None


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


class TMDBError(Exception):
    """Exception raised for TMDB API errors."""
    pass


class TMDBClient:
    """Client for TMDB API."""

    def __init__(
        self,
        api_key: str | None = None,
        cache: Cache | None = None,
        interactive_callback: Callable[[list[dict], str], int | None] | None = None,
        verbose: bool = False,
        language: str | None = None
    ):
        """
        Initialize TMDB client.

        Args:
            api_key: TMDB API key. If not provided, attempts to load from env/.env.
            cache: Cache instance for storing lookups.
            interactive_callback: Callback for interactive selection.
                                  Receives (results, title) and returns selected index or None.
            verbose: Enable verbose debug output.
            language: TMDB API language tag (e.g. "en-US"). Falls back to
                      DEFAULT_LANGUAGE when *None*.

        Raises:
            TMDBError: If API key is not found
        """
        self.api_key = api_key or load_api_key()
        if not self.api_key:
            raise TMDBError(
                "TMDB API key not found.\n"
                "Set it using one of these methods:\n"
                "  1. Environment variable: export TMDB_API_KEY=your_key\n"
                "  2. Create a .env file with: TMDB_API_KEY=your_key\n"
                "Get your free API key at: https://www.themoviedb.org/settings/api"
            )
        self.cache = cache or Cache()
        self.interactive_callback = interactive_callback
        self.verbose = verbose
        self.language = language or DEFAULT_LANGUAGE
        self._last_request_time = 0.0
        self.last_raw_results: list[dict] = []
        self._log(f"Using TMDB language: {self.language}")

    def _log(self, message: str) -> None:
        """Print debug message if verbose mode is enabled."""
        if self.verbose:
            print(f"  [TMDB] {message}")

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

        # Log the request (hide API key)
        log_params = {k: v for k, v in all_params.items() if k != "api_key"}
        self._log(f"GET {endpoint} params={log_params}")

        for attempt in range(retries):
            try:
                response = requests.get(url, params=all_params, timeout=DEFAULT_TIMEOUT)

                self._log(f"Response status: {response.status_code}")

                if response.status_code == 429:  # Rate limited
                    retry_after = int(response.headers.get("Retry-After", 1))
                    self._log(f"Rate limited, waiting {retry_after}s")
                    time.sleep(retry_after)
                    continue

                response.raise_for_status()
                data = response.json()
                if "results" in data:
                    self._log(f"Found {len(data['results'])} results")
                return data

            except requests.exceptions.Timeout:
                self._log(f"Timeout (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
                return None
            except requests.exceptions.RequestException as e:
                self._log(f"Request error: {e} (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
                return None

        return None

    def _score_results(
        self,
        results: list[dict],
        title: str,
        year: int | None = None,
        is_movie: bool = True,
    ) -> list[tuple[float, float, dict]]:
        """Score and sort results.

        Returns list of ``(rank_score, confidence, result_dict)`` sorted
        by rank_score descending.
        """
        if not results:
            return []

        title_norm = normalize_for_comparison(title)

        scored = []
        for result in results:
            title_field = "title" if is_movie else "name"
            original_title_field = "original_title" if is_movie else "original_name"
            date_field = "release_date" if is_movie else "first_air_date"

            result_title = result.get(title_field, "")
            original_title = result.get(original_title_field, "")

            result_title_norm = normalize_for_comparison(result_title)
            original_title_norm = normalize_for_comparison(original_title)

            # Calculate title similarity (use best of localized and original)
            title_sim = max(
                similarity_score(title, result_title),
                similarity_score(title, original_title)
            )

            # Exact title match bonus
            exact_match = (
                title_norm == result_title_norm
                or title_norm == original_title_norm
            )
            exact_bonus = 0.3 if exact_match else 0.0

            # Year bonus
            year_bonus = 0.0
            year_matched = False
            if year:
                result_date = result.get(date_field, "")
                if result_date and len(result_date) >= 4:
                    try:
                        result_year = int(result_date[:4])
                        if result_year == year:
                            year_bonus = 0.25
                            year_matched = True
                        elif abs(result_year - year) == 1:
                            year_bonus = 0.1
                    except ValueError:
                        pass

            # Popularity as tiebreaker (not part of confidence)
            popularity = result.get("popularity", 0)
            pop_bonus = min(popularity / 1000, 1.0) * 0.05

            # Total score for ranking
            score = title_sim + exact_bonus + year_bonus + pop_bonus

            # Confidence for this candidate (popularity excluded --
            # it helps ranking but not certainty)
            conf = 1.0 if exact_match else title_sim
            if year_matched:
                conf = min(1.0, conf + 0.1)

            scored.append((score, conf, result))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    def _choose_best_match(
        self,
        results: list[dict],
        title: str,
        year: int | None = None,
        is_movie: bool = True
    ) -> tuple[dict | None, float]:
        """
        Choose the best match from search results.

        Args:
            results: List of search results
            title: The title we're searching for
            year: Optional year to match
            is_movie: Whether we're searching for movies

        Returns:
            (best_result, confidence) where *confidence* is 0.0-1.0
            indicating how certain the match is.
        """
        if not results:
            return None, 0.0

        # If interactive mode and callback is set
        if self.interactive_callback and len(results) > 1:
            selected = self.interactive_callback(results, title)
            if selected is not None and 0 <= selected < len(results):
                return results[selected], 1.0

        scored = self._score_results(results, title, year, is_movie)
        if not scored:
            return None, 0.0

        return scored[0][2], scored[0][1]

    def scored_candidates(
        self,
        title: str,
        year: int | None = None,
        is_movie: bool = True,
        max_results: int = 5,
    ) -> list[dict]:
        """Return the top *max_results* from ``last_raw_results``, scored.

        Each returned dict is the raw TMDB result dict augmented with a
        ``_score`` key.  No API calls are made -- this reads from the
        results cached by the most recent ``search_movie`` /
        ``search_series`` call.
        """
        if not self.last_raw_results:
            return []

        title_norm = normalize_for_comparison(title)
        scored = []
        for result in self.last_raw_results:
            title_field = "title" if is_movie else "name"
            original_title_field = "original_title" if is_movie else "original_name"
            date_field = "release_date" if is_movie else "first_air_date"

            result_title = result.get(title_field, "")
            original_title = result.get(original_title_field, "")

            title_sim = max(
                similarity_score(title, result_title),
                similarity_score(title, original_title),
            )

            result_title_norm = normalize_for_comparison(result_title)
            original_title_norm = normalize_for_comparison(original_title)
            exact_match = (
                title_norm == result_title_norm
                or title_norm == original_title_norm
            )
            exact_bonus = 0.3 if exact_match else 0.0

            year_bonus = 0.0
            if year:
                result_date = result.get(date_field, "")
                if result_date and len(result_date) >= 4:
                    try:
                        result_year = int(result_date[:4])
                        if result_year == year:
                            year_bonus = 0.25
                        elif abs(result_year - year) == 1:
                            year_bonus = 0.1
                    except ValueError:
                        pass

            popularity = result.get("popularity", 0)
            pop_bonus = min(popularity / 1000, 1.0) * 0.05

            score = title_sim + exact_bonus + year_bonus + pop_bonus
            scored.append((score, result))

        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, r in scored[:max_results]:
            entry = dict(r)
            entry["_score"] = score
            out.append(entry)
        return out

    def search_movie_candidates(
        self, title: str, year: int | None = None, max_results: int = 5,
    ) -> list[tuple[dict, float]]:
        """Search movies, return scored ``(result_dict, confidence)`` list.

        No auto-select, no cache write.  Stores results in
        ``last_raw_results`` for later use by ``scored_candidates``.
        """
        params: dict[str, Any] = {"query": title}
        if year:
            params["year"] = year

        data = self._request("/search/movie", params)
        if not data or not data.get("results"):
            self.last_raw_results = []
            return []

        self.last_raw_results = data["results"]
        scored = self._score_results(data["results"], title, year, is_movie=True)
        return [
            (entry[2], entry[1]) for entry in scored[:max_results]
        ]

    def search_series_candidates(
        self, title: str, max_results: int = 5,
    ) -> list[tuple[dict, float]]:
        """Search series, return scored ``(result_dict, confidence)`` list.

        No auto-select, no cache write.  Stores results in
        ``last_raw_results`` for later use by ``scored_candidates``.
        """
        params: dict[str, Any] = {"query": title}

        data = self._request("/search/tv", params)
        if not data or not data.get("results"):
            self.last_raw_results = []
            return []

        self.last_raw_results = data["results"]
        scored = self._score_results(data["results"], title, is_movie=False)
        return [
            (entry[2], entry[1]) for entry in scored[:max_results]
        ]

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
            self.last_raw_results = []
            return None

        self.last_raw_results = data["results"]

        # Choose best match
        best, confidence = self._choose_best_match(
            data["results"], title, year, is_movie=True
        )
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
            overview=best.get("overview", ""),
            confidence=confidence
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
                overview=cached.get("overview", ""),
                original_language=cached.get("original_language", ""),
            )

        # Search TMDB
        params = {"query": title}
        data = self._request("/search/tv", params)
        if not data or not data.get("results"):
            self.last_raw_results = []
            return None

        self.last_raw_results = data["results"]

        # Choose best match
        best, confidence = self._choose_best_match(
            data["results"], title, is_movie=False
        )
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
            overview=best.get("overview", ""),
            confidence=confidence,
            original_language=best.get("original_language", ""),
        )

        # Cache result
        self.cache.set_series_search(title, {
            "id": series.id,
            "name": series.name,
            "original_name": series.original_name,
            "first_air_year": series.first_air_year,
            "overview": series.overview,
            "original_language": series.original_language,
        })
        self.cache.set_title_id(title, "series", series.id)

        return series

    def get_episode_details(
        self,
        series_id: int,
        season: int,
        episode: int,
        language: str | None = None,
    ) -> TMDBEpisode | None:
        """
        Get episode details from TMDB.

        Args:
            series_id: TMDB series ID
            season: Season number
            episode: Episode number
            language: Optional language override (e.g. "ja" or "en-US").
                      When *None*, uses the client's default language.

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
        params = {}
        if language:
            params["language"] = language
        data = self._request(endpoint, params=params or None)
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
