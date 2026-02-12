"""Settings management for RNMR GUI."""
import json
import os
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Platform-appropriate settings directory
# ---------------------------------------------------------------------------

def _settings_dir() -> Path:
    """Return the platform settings directory, creating it if needed."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / "RNMR"
    d.mkdir(parents=True, exist_ok=True)
    return d


SETTINGS_FILE = _settings_dir() / "settings.json"


# ---------------------------------------------------------------------------
# Template presets (unchanged -- consumed by the dialog)
# ---------------------------------------------------------------------------

DEFAULT_SERIES_TEMPLATE = "{title} - S{season:02d}E{episode:02d} - {episode_title}"
DEFAULT_MOVIE_TEMPLATE = "{title} ({year})"

SERIES_PRESETS = {
    "Standard": "{title} - S{season:02d}E{episode:02d} - {episode_title}",
    "Without Episode Title": "{title} - S{season:02d}E{episode:02d}",
    "Episode First": "S{season:02d}E{episode:02d} - {title} - {episode_title}",
    "Folder Style": "{title} - Season {season:02d} - E{episode:02d}",
    "Compact (1x04)": "{title} - {season}x{episode:02d} - {episode_title}",
    "Plex Style": "{title} - s{season:02d}e{episode:02d} - {episode_title}",
    "Custom": "",
}

MOVIE_PRESETS = {
    "Standard": "{title} ({year})",
    "Title Only": "{title}",
    "Year First": "({year}) {title}",
    "With Brackets": "[{year}] {title}",
    "Custom": "",
}

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


# ---------------------------------------------------------------------------
# Default values for every known key
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS: dict[str, Any] = {
    # Naming templates
    "series_template": DEFAULT_SERIES_TEMPLATE,
    "movie_template": DEFAULT_MOVIE_TEMPLATE,
    "series_preset": "Standard",
    "movie_preset": "Standard",

    # TMDB
    "tmdb_api_key": "",
    "tmdb_language": "en-US",

    # Behavior
    "ask_before_overwrite": True,
    "interactive_fallback": True,

    # State (not shown in settings dialog)
    "last_folder": "",
}


# ---------------------------------------------------------------------------
# SettingsManager -- single authority for reading / writing settings
# ---------------------------------------------------------------------------

class SettingsManager:
    """Centralised settings store backed by a JSON file.

    Usage:
        mgr = SettingsManager()
        key = mgr.get("tmdb_api_key")
        mgr.set("tmdb_api_key", "abc123")
        mgr.save()
    """

    _instance: "SettingsManager | None" = None

    def __new__(cls) -> "SettingsManager":
        """Singleton -- one instance per process."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data = cls._instance._load()
        return cls._instance

    # -- public API -------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        fallback = DEFAULT_SETTINGS.get(key, default)
        return self._data.get(key, fallback)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def save(self) -> bool:
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            return True
        except IOError:
            return False

    def all(self) -> dict[str, Any]:
        """Return a merged view: defaults + saved values."""
        merged = DEFAULT_SETTINGS.copy()
        merged.update(self._data)
        return merged

    def reload(self) -> None:
        self._data = self._load()

    # -- private ----------------------------------------------------------

    @staticmethod
    def _load() -> dict[str, Any]:
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}


# ---------------------------------------------------------------------------
# Backward-compatible free functions (thin wrappers around SettingsManager)
# ---------------------------------------------------------------------------

def load_settings() -> dict[str, Any]:
    """Load settings. Returns a dict with defaults for missing keys."""
    return SettingsManager().all()


def save_settings(settings: dict[str, Any]) -> bool:
    """Persist *settings* dict to disk."""
    mgr = SettingsManager()
    for k, v in settings.items():
        mgr.set(k, v)
    return mgr.save()


# ---------------------------------------------------------------------------
# Template helpers (unchanged)
# ---------------------------------------------------------------------------

def validate_template(template: str, template_type: str = "series") -> tuple[bool, str]:
    if not template or not template.strip():
        return False, "Template cannot be empty"
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
    return {
        "title": "The Matrix",
        "year": 1999,
        "original_title": "The Matrix",
        "ext": ".mkv",
    }


def render_template(template: str, data: dict[str, Any]) -> str:
    import re as _re

    result = template
    for key, value in data.items():
        result = result.replace(
            f"{{{key}:02d}}",
            f"{value:02d}" if isinstance(value, int) else str(value),
        )
        result = result.replace(
            f"{{{key}:02}}",
            f"{value:02d}" if isinstance(value, int) else str(value),
        )
        result = result.replace(f"{{{key}}}", str(value))

    remaining = _re.findall(r'\{(\w+)(?::[^}]*)?\}', result)
    if remaining:
        raise KeyError(remaining[0])

    return result
