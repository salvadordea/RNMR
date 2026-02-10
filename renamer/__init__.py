"""
RNMR - Media File Renamer

A CLI tool for renaming media files using TMDB metadata.
"""
from .models import ParsedMedia, TMDBMovie, TMDBSeries, TMDBEpisode, RenameResult
from .parser import parse_filename, is_media_file
from .tmdb import TMDBClient
from .formatter import format_series_name, format_movie_name
from .cache import Cache

__version__ = "1.0.0"
__all__ = [
    "ParsedMedia",
    "TMDBMovie",
    "TMDBSeries",
    "TMDBEpisode",
    "RenameResult",
    "parse_filename",
    "is_media_file",
    "TMDBClient",
    "format_series_name",
    "format_movie_name",
    "Cache",
]
