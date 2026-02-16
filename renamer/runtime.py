"""Runtime path resolution for PyInstaller compatibility.

When the application is bundled with PyInstaller (--onefile), all data
files are extracted to a temporary directory referenced by
``sys._MEIPASS``.  This module provides helpers that transparently
resolve paths in both the development and frozen environments.
"""

import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# Cached after the first probe -- None means "not checked yet".
_ffprobe_available: bool | None = None
_ffprobe_path: str | None = None


def resource_path(relative_path: str) -> Path:
    """Resolve *relative_path* to a bundled resource.

    In a PyInstaller bundle ``sys._MEIPASS`` points to the extraction
    directory.  During normal development the project root (one level
    above this file's package) is used instead.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent
    return base / relative_path


def get_ffprobe_path() -> str:
    """Return the path to the ffprobe executable.

    Checks for a bundled ``ffprobe.exe`` first (PyInstaller bundle or
    ``resources/`` directory in the project tree).  Falls back to the
    bare command name so the OS can resolve it via ``PATH``.
    """
    global _ffprobe_path
    if _ffprobe_path is not None:
        return _ffprobe_path

    bundled = resource_path("resources") / "ffprobe.exe"
    if bundled.is_file():
        _ffprobe_path = str(bundled)
    else:
        _ffprobe_path = "ffprobe"
    return _ffprobe_path


def is_ffprobe_available() -> bool:
    """Test whether ffprobe can be executed.

    The result is cached for the lifetime of the process.  Returns
    *False* (and logs a warning) when ffprobe is missing or broken.
    """
    global _ffprobe_available
    if _ffprobe_available is not None:
        return _ffprobe_available

    path = get_ffprobe_path()
    try:
        kwargs: dict = {
            "capture_output": True,
            "timeout": 5,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        subprocess.run([path, "-version"], **kwargs)
        _ffprobe_available = True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        _ffprobe_available = False
        log.warning(
            "ffprobe not found -- embedded-metadata fallback disabled"
        )

    return _ffprobe_available
