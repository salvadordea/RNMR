"""
RNMR - Media File Renamer

A CLI tool for renaming media files using TMDB metadata.
"""
from .models import (
    ParsedMedia,
    TMDBMovie,
    TMDBSeries,
    TMDBEpisode,
    RenameResult,
    SubtitleFile
)
from .parser import (
    parse_filename,
    is_media_file,
    is_subtitle_file,
    find_associated_subtitles
)
from .tmdb import TMDBClient, TMDBError
from .formatter import (
    format_series_name,
    format_movie_name,
    format_subtitle_name
)
from .cache import Cache

__version__ = "0.9.1"
__all__ = [
    "ParsedMedia",
    "TMDBMovie",
    "TMDBSeries",
    "TMDBEpisode",
    "RenameResult",
    "SubtitleFile",
    "parse_filename",
    "is_media_file",
    "is_subtitle_file",
    "find_associated_subtitles",
    "TMDBClient",
    "TMDBError",
    "format_series_name",
    "format_movie_name",
    "format_subtitle_name",
    "Cache",
]
