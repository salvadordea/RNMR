"""Parser module for extracting media information from file names."""
import re
from pathlib import Path
from .models import ParsedMedia


# Patterns to remove (noise)
NOISE_PATTERNS = [
    # Quality
    r'\b(720p|1080p|2160p|4k|uhd)\b',
    # Source
    r'\b(web[- ]?dl|webrip|blu[- ]?ray|bdrip|brrip|hdtv|hdrip|dvdrip|dvd)\b',
    # Codec
    r'\b(x264|x265|h\.?264|h\.?265|hevc|avc|xvid|divx)\b',
    # Audio
    r'\b(aac|ac3|dts|dd5\.?1|atmos|truehd)\b',
    # Language/subtitle tags
    r'\b(dual[- ]?lat|latino|castellano|spanish|english|sub(bed|s)?|multi)\b',
    # HDR
    r'\b(hdr|hdr10\+?|dolby[- ]?vision|dv)\b',
    # Other common tags
    r'\b(repack|proper|extended|unrated|directors?[- ]?cut|theatrical)\b',
    r'\b(remux|hybrid)\b',
    # Release group patterns (at the end, after dash or in brackets)
    r'-[a-z0-9]+$',
    r'\[[^\]]+\]',
    r'\([^)]*(?:rip|sub|dub|lat)[^)]*\)',
]

# Episode patterns (order matters - more specific first)
EPISODE_PATTERNS = [
    # S01E04E05 (multi-episode)
    r'[sS](\d{1,2})[eE](\d{1,2})(?:[eE](\d{1,2}))+',
    # S01E04
    r'[sS](\d{1,2})[eE](\d{1,2})',
    # S1E4
    r'[sS](\d{1,2})[eE](\d{1,2})',
    # 1x04
    r'(\d{1,2})x(\d{2})',
    # Season 1 Episode 4
    r'[sS]eason\s*(\d{1,2})\s*[eE]pisode\s*(\d{1,2})',
]

# Year pattern
YEAR_PATTERN = r'\b((?:19|20)\d{2})\b'


def normalize_separators(name: str) -> str:
    """Replace common separators with spaces."""
    # Replace dots, underscores, and dashes with spaces
    normalized = re.sub(r'[._]', ' ', name)
    # Replace multiple dashes with space (but keep single dash for episode ranges)
    normalized = re.sub(r'--+', ' ', normalized)
    # Normalize multiple spaces
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized.strip()


def remove_noise(name: str) -> str:
    """Remove quality, codec, and release group tags."""
    result = name
    for pattern in NOISE_PATTERNS:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)
    # Clean up multiple spaces
    result = re.sub(r'\s+', ' ', result)
    return result.strip()


def extract_episodes(name: str) -> tuple[int | None, list[int], str]:
    """
    Extract season and episode numbers from name.
    Returns (season, episodes_list, remaining_name).
    """
    # Try multi-episode pattern first: S01E04E05
    multi_ep_pattern = r'[sS](\d{1,2})[eE](\d{1,2})([eE]\d{1,2})+'
    match = re.search(multi_ep_pattern, name)
    if match:
        season = int(match.group(1))
        # Extract all episode numbers
        full_match = match.group(0)
        episodes = [int(ep) for ep in re.findall(r'[eE](\d{1,2})', full_match)]
        remaining = name[:match.start()] + name[match.end():]
        return season, episodes, remaining.strip()

    # Try standard patterns
    for pattern in EPISODE_PATTERNS[1:]:  # Skip the multi-episode pattern
        match = re.search(pattern, name)
        if match:
            season = int(match.group(1))
            episode = int(match.group(2))
            remaining = name[:match.start()] + name[match.end():]
            return season, [episode], remaining.strip()

    return None, [], name


def extract_year(name: str) -> tuple[int | None, str]:
    """
    Extract year from name.
    Returns (year, remaining_name).
    """
    matches = list(re.finditer(YEAR_PATTERN, name))
    if matches:
        # Take the last year found (usually the release year, not part of title)
        match = matches[-1]
        year = int(match.group(1))
        # Only consider it a valid year if it's reasonable
        if 1900 <= year <= 2100:
            remaining = name[:match.start()] + name[match.end():]
            return year, remaining.strip()
    return None, name


def clean_title(title: str) -> str:
    """Clean up the title guess."""
    # Remove leading/trailing dashes and spaces
    title = re.sub(r'^[\s\-]+|[\s\-]+$', '', title)
    # Remove empty parentheses or brackets
    title = re.sub(r'\(\s*\)|\[\s*\]', '', title)
    # Normalize spaces
    title = re.sub(r'\s+', ' ', title)
    return title.strip()


def parse_filename(filepath: str | Path) -> ParsedMedia:
    """
    Parse a media filename and extract metadata.

    Args:
        filepath: Path to the media file

    Returns:
        ParsedMedia object with extracted information
    """
    path = Path(filepath)
    # Get filename without extension
    raw_name = path.stem

    # Normalize separators first
    name = normalize_separators(raw_name)

    # Extract episode information
    season, episodes, name = extract_episodes(name)

    # Determine media type
    if season is not None and episodes:
        media_type = "series"
    else:
        media_type = "movie"

    # Extract year
    year, name = extract_year(name)

    # Remove noise
    name = remove_noise(name)

    # Clean up title
    title_guess = clean_title(name)

    # If title is empty, use original name
    if not title_guess:
        title_guess = clean_title(normalize_separators(raw_name))

    return ParsedMedia(
        raw_name=raw_name,
        title_guess=title_guess,
        media_type=media_type,
        season=season,
        episodes=episodes,
        year=year
    )


def is_media_file(filepath: Path) -> bool:
    """Check if file is a media file based on extension."""
    media_extensions = {
        '.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm',
        '.m4v', '.mpg', '.mpeg', '.m2ts', '.ts', '.vob', '.ogm'
    }
    return filepath.suffix.lower() in media_extensions
