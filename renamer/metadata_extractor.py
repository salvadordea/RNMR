"""Extract metadata from media files using ffprobe.

Standalone module -- no Qt, no TMDB imports.  Used as a last-resort
fallback when the filename-based TMDB search fails: many media files
embed the real title in container metadata (Matroska tags, MP4 atoms,
etc.) that ffprobe can read.

Design constraints:
  - Never block the UI thread (caller is responsible for threading).
  - Never show a console window (CREATE_NO_WINDOW on Windows).
  - 5-second timeout per invocation, at most one retry.
  - Graceful degradation: returns ``{}`` on any failure.
"""

import json
import logging
import re
import subprocess
import sys
from pathlib import Path

from renamer.runtime import get_ffprobe_path, is_ffprobe_available

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Subprocess flags -- prevent console window on Windows
# ---------------------------------------------------------------------------

_SUBPROCESS_KWARGS: dict = {}
if sys.platform == "win32":
    _SUBPROCESS_KWARGS["creationflags"] = subprocess.CREATE_NO_WINDOW

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TIMEOUT = 5  # seconds per attempt
_MAX_ATTEMPTS = 2  # initial call + one retry

# Tags to extract, in priority order for title selection.
_TAG_KEYS = (
    "format_title",
    "stream_title",
    "format_description",
    "format_comment",
    "format_artist",
    "format_encoder",
)

# Generic / tool strings that should never be treated as titles.
_REJECT_EXACT = {
    "video", "audio", "media", "untitled", "new project", "track",
    "output", "default", "sample", "test", "clip", "recording",
}

_REJECT_PREFIXES = (
    "vid_", "img_", "dsc_", "mov_", "rec_", "cap_",
)

_REJECT_TOOL_RE = re.compile(
    r'\b(?:ffmpeg|handbrake|mkvmerge|mkvtoolnix|libx264|libx265'
    r'|lavf|lavc|lame|x264|x265|xvid|divx|hevc|avc'
    r'|matroska|webm|mp4box|gpac)\b',
    re.IGNORECASE,
)

# Year pattern (19xx or 20xx).
_YEAR_RE = re.compile(r'\b(?:19|20)\d{2}\b')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_metadata(filepath: str | Path) -> dict[str, str]:
    """Run ffprobe on *filepath* and return a flat dict of tag values.

    Returns ``{}`` when ffprobe is unavailable, the file does not
    exist, or any error occurs (timeout, corrupt file, etc.).
    """
    if not is_ffprobe_available():
        return {}

    filepath = Path(filepath)
    if not filepath.is_file():
        return {}

    data = _run_ffprobe(filepath)
    if data is None:
        return {}

    tags: dict[str, str] = {}

    # Format-level tags
    fmt_tags = data.get("format", {}).get("tags", {})
    for key in ("title", "comment", "description", "artist", "encoder"):
        val = fmt_tags.get(key) or fmt_tags.get(key.upper())
        if val and val.strip():
            tags[f"format_{key}"] = val.strip()

    # Stream-level tags (first video stream with a title wins)
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            s_tags = stream.get("tags", {})
            val = s_tags.get("title") or s_tags.get("TITLE")
            if val and val.strip():
                tags.setdefault("stream_title", val.strip())
                break

    return tags


def is_plausible_title(text: str) -> bool:
    """Return True when *text* looks like a real media title.

    Accepts text that has >= 3 words, OR contains a year (19xx/20xx), OR
    is two capitalised words.  Rejects generic strings, codec names, and
    tool names.
    """
    if not text or not text.strip():
        return False

    text = text.strip()

    # Reject known generics
    if text.lower() in _REJECT_EXACT:
        return False

    if text.lower().startswith(_REJECT_PREFIXES):
        return False

    # Reject tool / codec names
    if _REJECT_TOOL_RE.search(text):
        return False

    # Reject strings that look like auto-generated camera filenames
    # e.g. "VID_20260101_123456", "DSC00123"
    if re.match(r'^[A-Z]{2,5}[\d_]+$', text):
        return False

    words = text.split()

    # 3+ words -> plausible
    if len(words) >= 3:
        return True

    # Contains a year -> plausible
    if _YEAR_RE.search(text):
        return True

    # 2 capitalised words -> plausible (e.g. "Breaking Bad")
    if len(words) == 2 and all(w[0].isupper() for w in words if w):
        return True

    return False


def find_best_title(tags: dict[str, str]) -> str | None:
    """Return the first plausible title from *tags*, or None.

    Iterates tags in priority order:
    format.title > stream.title > format.description > format.comment >
    format.artist > format.encoder.
    """
    for key in _TAG_KEYS:
        val = tags.get(key)
        if val and is_plausible_title(val):
            return val
    return None


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _run_ffprobe(filepath: Path) -> dict | None:
    """Execute ffprobe with retry.  Returns parsed JSON or None."""
    cmd = [
        get_ffprobe_path(),
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(filepath),
    ]

    for attempt in range(_MAX_ATTEMPTS):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
                **_SUBPROCESS_KWARGS,
            )
        except subprocess.TimeoutExpired:
            log.debug(
                "ffprobe timeout (attempt %d/%d): %s",
                attempt + 1, _MAX_ATTEMPTS, filepath.name,
            )
            continue
        except (FileNotFoundError, OSError) as exc:
            log.debug("ffprobe error: %s", exc)
            return None

        if result.returncode != 0:
            return None

        try:
            return json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            return None

    return None
