"""Data models for the renamer package."""
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ParsedMedia:
    """Represents parsed media file information."""
    raw_name: str
    title_guess: str
    media_type: Literal["series", "movie"]
    season: int | None = None
    episodes: list[int] = field(default_factory=list)
    year: int | None = None


@dataclass
class TMDBMovie:
    """Represents a movie from TMDB."""
    id: int
    title: str
    original_title: str
    year: int | None
    overview: str = ""


@dataclass
class TMDBSeries:
    """Represents a TV series from TMDB."""
    id: int
    name: str
    original_name: str
    first_air_year: int | None
    overview: str = ""


@dataclass
class TMDBEpisode:
    """Represents an episode from TMDB."""
    series_id: int
    season_number: int
    episode_number: int
    name: str
    overview: str = ""


@dataclass
class RenameResult:
    """Represents a rename operation result."""
    original_path: str
    new_path: str
    success: bool
    error: str | None = None
    skipped: bool = False
    skip_reason: str | None = None
