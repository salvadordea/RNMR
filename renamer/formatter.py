"""Formatter module for generating final file names."""
import re
from pathlib import Path

from .models import ParsedMedia, TMDBMovie, TMDBSeries, TMDBEpisode, SubtitleFile


def sanitize_filename(name: str) -> str:
    """
    Remove or replace characters that are invalid in file names.

    Args:
        name: The name to sanitize

    Returns:
        Sanitized name safe for use as a filename
    """
    # Characters not allowed in Windows filenames: / \ : * ? " < > |
    invalid_chars = r'[<>:"/\\|?*]'
    # Replace with empty string
    sanitized = re.sub(invalid_chars, '', name)
    # Remove leading/trailing dots and spaces
    sanitized = sanitized.strip('. ')
    # Replace multiple spaces with single space
    sanitized = re.sub(r'\s+', ' ', sanitized)
    return sanitized


def format_episode_code(season: int, episodes: list[int]) -> str:
    """
    Format season and episode numbers.

    Args:
        season: Season number
        episodes: List of episode numbers

    Returns:
        Formatted episode code (e.g., 'S01E04' or 'S01E04E05')
    """
    if not episodes:
        return f"S{season:02d}"

    episode_parts = ''.join(f"E{ep:02d}" for ep in sorted(episodes))
    return f"S{season:02d}{episode_parts}"


def is_multi_episode(episodes: list[int]) -> bool:
    """Check if this is a multi-episode file."""
    return len(episodes) > 1


def format_series_name(
    series: TMDBSeries,
    season: int,
    episodes: list[int],
    episode_details: list[TMDBEpisode] | None = None,
    extension: str = "",
    include_episode_title: bool = True
) -> str:
    """
    Format a series episode filename.

    Format: {Original Series Title} - S{season:02}E{episode:02} - {Episode Name}.ext

    For multi-episode files, episode title is NOT included.

    Args:
        series: TMDB series info
        season: Season number
        episodes: List of episode numbers
        episode_details: Optional episode details for titles
        extension: File extension (including dot)
        include_episode_title: Whether to include episode title

    Returns:
        Formatted filename
    """
    # PRIORITY: Use original_name first, fallback to localized name
    series_title = series.original_name if series.original_name else series.name
    series_title = sanitize_filename(series_title)

    # Format episode code
    ep_code = format_episode_code(season, episodes)

    # Build filename
    parts = [series_title, ep_code]

    # For multi-episode files, NEVER include episode title
    if is_multi_episode(episodes):
        include_episode_title = False

    # Add episode title if requested and available (single episode only)
    if include_episode_title and episode_details and len(episode_details) == 1:
        ep_title = sanitize_filename(episode_details[0].name)
        if ep_title:
            parts.append(ep_title)

    filename = " - ".join(parts)
    return f"{filename}{extension}"


def format_movie_name(
    movie: TMDBMovie,
    extension: str = "",
    keep_year: bool = True
) -> str:
    """
    Format a movie filename.

    Format: {Original Title} ({Year}).ext

    Args:
        movie: TMDB movie info
        extension: File extension (including dot)
        keep_year: Whether to include the year

    Returns:
        Formatted filename
    """
    # PRIORITY: Use original_title first, fallback to localized title
    title = movie.original_title if movie.original_title else movie.title
    title = sanitize_filename(title)

    if keep_year and movie.year:
        filename = f"{title} ({movie.year})"
    else:
        filename = title

    return f"{filename}{extension}"


def format_fallback(
    parsed: ParsedMedia,
    extension: str = ""
) -> str:
    """
    Format filename without TMDB data.

    Args:
        parsed: Parsed media information
        extension: File extension (including dot)

    Returns:
        Formatted filename
    """
    title = sanitize_filename(parsed.title_guess)

    if parsed.media_type == "series" and parsed.season is not None:
        ep_code = format_episode_code(parsed.season, parsed.episodes)
        filename = f"{title} - {ep_code}"
    elif parsed.year:
        filename = f"{title} ({parsed.year})"
    else:
        filename = title

    return f"{filename}{extension}"


def format_subtitle_name(
    new_video_basename: str,
    subtitle: SubtitleFile
) -> str:
    """
    Format a subtitle filename based on the new video name.

    Args:
        new_video_basename: New video filename without extension
        subtitle: SubtitleFile with language suffix info

    Returns:
        New subtitle filename with preserved language suffix
    """
    if subtitle.language_suffix:
        return f"{new_video_basename}.{subtitle.language_suffix}{subtitle.extension}"
    return f"{new_video_basename}{subtitle.extension}"


def get_new_path(
    original_path: Path,
    new_filename: str
) -> Path:
    """
    Get the new full path for a renamed file.

    Args:
        original_path: Original file path
        new_filename: New filename (with extension)

    Returns:
        New full path
    """
    return original_path.parent / new_filename


def paths_are_equivalent(path1: Path, path2: Path) -> bool:
    """
    Check if two paths point to the same location.

    Args:
        path1: First path
        path2: Second path

    Returns:
        True if paths are equivalent
    """
    try:
        return path1.resolve() == path2.resolve()
    except OSError:
        return str(path1) == str(path2)


def filenames_match(name1: str, name2: str) -> bool:
    """
    Check if two filenames are essentially the same.

    Args:
        name1: First filename
        name2: Second filename

    Returns:
        True if filenames match (case-insensitive)
    """
    return name1.lower().strip() == name2.lower().strip()
