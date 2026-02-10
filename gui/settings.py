"""Settings management for RNMR GUI."""
import json
from pathlib import Path
from typing import Any

# Settings file location
SETTINGS_FILE = Path(__file__).parent.parent / "settings.json"

# Default templates
DEFAULT_SERIES_TEMPLATE = "{title} - S{season:02d}E{episode:02d} - {episode_title}"
DEFAULT_MOVIE_TEMPLATE = "{title} ({year})"

# Template presets for series
SERIES_PRESETS = {
    "Standard": "{title} - S{season:02d}E{episode:02d} - {episode_title}",
    "Without Episode Title": "{title} - S{season:02d}E{episode:02d}",
    "Episode First": "S{season:02d}E{episode:02d} - {title} - {episode_title}",
    "Folder Style": "{title} - Season {season:02d} - E{episode:02d}",
    "Compact (1x04)": "{title} - {season}x{episode:02d} - {episode_title}",
    "Plex Style": "{title} - s{season:02d}e{episode:02d} - {episode_title}",
    "Custom": "",
}

# Template presets for movies
MOVIE_PRESETS = {
    "Standard": "{title} ({year})",
    "Title Only": "{title}",
    "Year First": "({year}) {title}",
    "With Brackets": "[{year}] {title}",
    "Custom": "",
}

# Available template variables
TEMPLATE_VARIABLES = {
    "series": [
        ("{title}", "Series title from TMDB"),
        ("{season}", "Season number (1, 2, 3...)"),
        ("{season:02d}", "Season number zero-padded (01, 02...)"),
        ("{episode}", "Episode number (1, 2, 3...)"),
        ("{episode:02d}", "Episode number zero-padded (01, 02...)"),
        ("{episode_title}", "Episode name from TMDB"),
        ("{year}", "First air year"),
        ("{episodes}", "All episode numbers (for multi-ep: 01E02)"),
    ],
    "movie": [
        ("{title}", "Movie title from TMDB"),
        ("{year}", "Release year"),
        ("{original_title}", "Original language title"),
    ],
}

# Default settings
DEFAULT_SETTINGS = {
    "series_template": DEFAULT_SERIES_TEMPLATE,
    "movie_template": DEFAULT_MOVIE_TEMPLATE,
    "series_preset": "Standard",
    "movie_preset": "Standard",
}


def load_settings() -> dict[str, Any]:
    """
    Load settings from settings.json.

    Returns:
        Settings dictionary with defaults for missing keys.
    """
    settings = DEFAULT_SETTINGS.copy()

    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                settings.update(saved)
        except (json.JSONDecodeError, IOError):
            pass

    return settings


def save_settings(settings: dict[str, Any]) -> bool:
    """
    Save settings to settings.json.

    Args:
        settings: Settings dictionary to save.

    Returns:
        True if saved successfully, False otherwise.
    """
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        return True
    except IOError:
        return False


def validate_template(template: str, template_type: str = "series") -> tuple[bool, str]:
    """
    Validate a template string.

    Args:
        template: The template to validate.
        template_type: "series" or "movie"

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not template or not template.strip():
        return False, "Template cannot be empty"

    # Try to format with sample data
    try:
        sample = get_sample_data(template_type)
        result = render_template(template, sample)
        if not result:
            return False, "Template produced empty result"
        return True, ""
    except KeyError as e:
        return False, f"Unknown variable: {e}"
    except ValueError as e:
        return False, f"Format error: {e}"
    except Exception as e:
        return False, f"Invalid template: {e}"


def get_sample_data(template_type: str = "series") -> dict[str, Any]:
    """Get sample data for template preview."""
    if template_type == "series":
        return {
            "title": "The Night Manager",
            "season": 1,
            "episode": 5,
            "episode_title": "Episode 5",
            "year": 2016,
            "episodes": "05",
            "ext": ".mkv",
        }
    else:
        return {
            "title": "The Matrix",
            "year": 1999,
            "original_title": "The Matrix",
            "ext": ".mkv",
        }


def render_template(template: str, data: dict[str, Any]) -> str:
    """
    Render a template with given data.

    Args:
        template: The template string.
        data: Data dictionary.

    Returns:
        Rendered string.
    """
    # Handle format specifiers manually for flexibility
    result = template

    for key, value in data.items():
        # Handle zero-padded formats like {season:02d}
        result = result.replace(f"{{{key}:02d}}", f"{value:02d}" if isinstance(value, int) else str(value))
        result = result.replace(f"{{{key}:02}}", f"{value:02d}" if isinstance(value, int) else str(value))
        # Handle plain replacement
        result = result.replace(f"{{{key}}}", str(value))

    # Check for any remaining unreplaced variables
    import re
    remaining = re.findall(r'\{(\w+)(?::[^}]*)?\}', result)
    if remaining:
        raise KeyError(remaining[0])

    return result
