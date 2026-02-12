"""Parser module for extracting media information from file names."""
import re
from pathlib import Path
from .models import ParsedMedia, SubtitleFile


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
    # S01E04 / S1E4
    r'[sS](\d{1,2})[eE](\d{1,2})',
    # 1x04, 1x4, 01x05 (supports 1-2 digits for both season and episode)
    r'\b(\d{1,2})x(\d{1,2})\b',
    # Season 1 Episode 4
    r'[sS]eason\s*(\d{1,2})\s*[eE]pisode\s*(\d{1,2})',
]

# Year pattern
YEAR_PATTERN = r'\b((?:19|20)\d{2})\b'

# Subtitle extensions
SUBTITLE_EXTENSIONS = {'.srt', '.sub', '.ass', '.ssa', '.vtt'}

# Common language codes for subtitles
LANGUAGE_CODES = {
    'en', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'ja', 'ko', 'zh',
    'ar', 'nl', 'pl', 'tr', 'vi', 'th', 'id', 'hi', 'he', 'cs',
    'eng', 'spa', 'fra', 'deu', 'ita', 'por', 'rus', 'jpn', 'kor', 'zho',
    'lat', 'forced', 'sdh', 'cc'
}


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
        # Keep only text before the episode pattern; content after is
        # episode title or quality tags, not part of the series title.
        remaining = name[:match.start()]
        return season, episodes, remaining.strip()

    # Try standard patterns
    for pattern in EPISODE_PATTERNS[1:]:  # Skip the multi-episode pattern
        match = re.search(pattern, name)
        if match:
            season = int(match.group(1))
            episode = int(match.group(2))
            remaining = name[:match.start()]
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


def is_subtitle_file(filepath: Path) -> bool:
    """Check if file is a subtitle file based on extension."""
    # Handle compound extensions like .en.srt
    suffixes = filepath.suffixes
    if suffixes:
        return suffixes[-1].lower() in SUBTITLE_EXTENSIONS
    return False


def get_subtitle_base_name(filepath: Path) -> str:
    """
    Get the base name of a subtitle file without language suffix.

    For "Show.S01E04.en.srt" returns "Show.S01E04"
    For "Show.S01E04.srt" returns "Show.S01E04"
    """
    name = filepath.name
    suffixes = filepath.suffixes

    if len(suffixes) >= 2:
        # Check if second-to-last suffix is a language code
        potential_lang = suffixes[-2].lstrip('.')
        if potential_lang.lower() in LANGUAGE_CODES:
            # Remove both language and subtitle extension
            return filepath.stem.rsplit('.', 1)[0]

    # Just remove the subtitle extension
    return filepath.stem


def parse_subtitle_file(filepath: Path) -> SubtitleFile:
    """
    Parse a subtitle file path to extract language suffix and extension.

    Args:
        filepath: Path to the subtitle file

    Returns:
        SubtitleFile with path, language suffix, and extension
    """
    suffixes = filepath.suffixes
    language_suffix = ""
    extension = suffixes[-1] if suffixes else ""

    if len(suffixes) >= 2:
        potential_lang = suffixes[-2].lstrip('.')
        if potential_lang.lower() in LANGUAGE_CODES:
            language_suffix = potential_lang

    return SubtitleFile(
        path=str(filepath),
        language_suffix=language_suffix,
        extension=extension
    )


def find_associated_subtitles(video_path: Path) -> list[SubtitleFile]:
    """
    Find subtitle files associated with a video file.

    Only matches subtitles with EXACT same base name as the video.

    Args:
        video_path: Path to the video file

    Returns:
        List of SubtitleFile objects
    """
    video_stem = video_path.stem
    parent_dir = video_path.parent
    subtitles = []

    if not parent_dir.exists():
        return subtitles

    for file in parent_dir.iterdir():
        if not file.is_file():
            continue
        if not is_subtitle_file(file):
            continue

        # Get the base name of the subtitle (without language suffix)
        sub_base = get_subtitle_base_name(file)

        # Exact match required
        if sub_base == video_stem:
            subtitles.append(parse_subtitle_file(file))

    return subtitles
