# RNMR - Media File Renamer

A desktop application and CLI tool for renaming media files (movies and TV series) using TMDB metadata.

## Features

- **Desktop GUI** with dark theme, powered by PySide6
- **First-run setup wizard** for TMDB API key configuration
- Automatic detection of movies and TV series
- Episode pattern recognition (S01E04, 1x04, S01E04E05, etc.)
- TMDB integration for official titles and episode names
- **Interactive TMDB selection** -- search, filter by media type, and pick the correct match from within the modal
- **Detection state machine** -- clean separation of TMDB lookup logic from UI
- **Original title priority** - uses original language titles by default
- **Subtitle support** - automatically renames associated .srt files
- **Persistent undo** -- SQLite-backed rename history; undo the last batch rename at any time
- **ffprobe metadata fallback** -- extracts embedded titles when filename parsing fails
- Local caching to minimize API calls
- Smart title matching using similarity scoring
- **Manual TMDB ID disambiguation** - set specific IDs for problematic files
- Dry-run mode for safe previewing
- Confirmation prompt before renaming
- File limit for batch processing
- Recursive directory processing
- **Standalone Windows executable** via PyInstaller

## Requirements

- Python 3.10+
- TMDB API key (free at https://www.themoviedb.org/settings/api)

## Installation

```bash
git clone https://github.com/salvadordea/RNMR.git
cd RNMR
pip install -e .
```

Or install dependencies directly:

```bash
pip install -r requirements.txt
```

## Configuration

Set your TMDB API key using one of these methods:

### Option 1: Environment Variable

```bash
# Linux/macOS
export TMDB_API_KEY=your_key_here

# Windows (PowerShell)
$env:TMDB_API_KEY="your_key_here"

# Windows (CMD)
set TMDB_API_KEY=your_key_here
```

### Option 2: .env File

Create a `.env` file in your current directory or home directory:

```
TMDB_API_KEY=your_key_here
```

## Usage

### Basic Usage

```bash
# Preview renames (dry run)
python -m renamer /path/to/media --dry-run

# Rename with TMDB metadata
python -m renamer /path/to/media --use-tmdb

# Recursive processing with dry run
python -m renamer /path/to/media --recursive --use-tmdb --dry-run

# With confirmation prompt
python -m renamer /path/to/media --use-tmdb --confirm

# Limit to first 10 files
python -m renamer /path/to/media --use-tmdb --limit 10
```

### Options

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview changes without renaming |
| `--recursive`, `-r` | Process directories recursively |
| `--use-tmdb` | Use TMDB for metadata lookup |
| `--interactive`, `-i` | Interactively choose from multiple matches |
| `--keep-year` | Include year in movie names (default) |
| `--no-year` | Don't include year in movie names |
| `--no-episode-title` | Don't include episode title in series names |
| `--confirm` | Ask for confirmation before renaming |
| `--limit N` | Limit number of files to process |
| `--language LANG` | Language for TMDB results (default: es-MX) |
| `--cache-dir PATH` | Directory for cache file |

### Examples

```bash
# Process a single file
python -m renamer "Breaking.Bad.S01E01.720p.BluRay.x264.mkv" --use-tmdb --dry-run

# Process a directory with interactive mode
python -m renamer /media/series --recursive --use-tmdb --interactive

# Process without episode titles
python -m renamer /media/series --use-tmdb --no-episode-title

# Process with confirmation
python -m renamer /media/series --use-tmdb --confirm
```

### Output Format

**Series (single episode):**
```
{Original Series Title} - S{season:02}E{episode:02} - {Episode Name}.ext
```
Example: `A Knight of the Seven Kingdoms - S01E04 - The Oath.mkv`

**Series (multi-episode):**
```
{Original Series Title} - S{season:02}E{episode:02}E{episode:02}.ext
```
Example: `Breaking Bad - S01E04E05.mkv`

Note: Episode titles are NOT included for multi-episode files.

**Movies:**
```
{Original Title} ({Year}).ext
```
Example: `The Matrix (1999).mkv`

### Subtitle Handling

When renaming a video file, the tool automatically finds and renames associated subtitle files:

**Before:**
```
Show.S01E04.mkv
Show.S01E04.en.srt
Show.S01E04.es.srt
```

**After:**
```
Show - S01E04 - Episode Name.mkv
Show - S01E04 - Episode Name.en.srt
Show - S01E04 - Episode Name.es.srt
```

Rules:
- Only subtitles with EXACT matching base name are renamed
- Language suffixes are preserved (.en.srt, .es.srt, etc.)
- Respects --dry-run flag

### Output Example

```
python renamer.py /media --recursive --use-tmdb --dry-run

Found 2 media file(s)
[DRY RUN - no files will be renamed]

Video:
  El.caballero.de.los.Siete.Reinos.S01E04.2026.WEB-DL.mkv
  -> A Knight of the Seven Kingdoms - S01E04 - The Oath.mkv
Subtitle:
  El.caballero.de.los.Siete.Reinos.S01E04.en.srt
  -> A Knight of the Seven Kingdoms - S01E04 - The Oath.en.srt

Video:
  The.Matrix.1999.BluRay.1080p.mkv
  -> The Matrix (1999).mkv

--------------------------------------------------
Would rename: 3 files
```

## Title Priority

The tool prioritizes **original language titles** over localized titles:

- For TV Series: Uses `original_name` from TMDB
- For Movies: Uses `original_title` from TMDB

This ensures consistency regardless of your locale settings.

## Detected Patterns

The parser recognizes:
- `S01E04`, `s01e04`, `S1E4`
- `1x04`
- `S01E04E05` (multi-episode)
- `Season 1 Episode 4`

Noise removal includes:
- Quality tags (720p, 1080p, 2160p, 4K)
- Source tags (WEB-DL, BluRay, HDTV)
- Codec tags (x264, x265, H.264, HEVC)
- Language tags (Dual-Lat, Latino, Sub)
- Release groups

## Cache

The tool creates a `.renamer_cache.json` file to store TMDB lookups:

- Title to TMDB ID mappings
- Movie search results
- Series search results
- Episode details (including episode titles)

This avoids repeated API calls for the same content.

## Manual ID Disambiguation

When automatic TMDB matching fails or returns the wrong result, you can manually set the TMDB ID:

### GUI
Right-click on any file in the table and select "Set TMDB ID..." to open the disambiguation dialog. Supported formats:
- TMDB ID: `12345`
- With type: `tv:12345` or `movie:12345`
- TMDB URL: `https://themoviedb.org/tv/12345`

The ID will be verified against TMDB before saving. Manual mappings are stored in `.rnmr_ids.json` in the scanned folder.

### How It Works
1. Right-click a file that was incorrectly matched
2. Enter the correct TMDB ID (find it on themoviedb.org)
3. Click "Verify ID" to confirm
4. Click "Save" to store the mapping
5. Rescan to apply the correct metadata

Manual IDs take priority over automatic TMDB search results.

## Building a Standalone Executable (Windows)

RNMR can be packaged as a single `.exe` file that runs on any Windows
machine without Python installed.

### Prerequisites

```bash
pip install pyinstaller PySide6 requests python-dotenv
```

### Bundling ffprobe (optional)

If you want embedded-metadata extraction to work out of the box, place
a copy of `ffprobe.exe` in the `resources/` directory before building.
You can get it from [ffmpeg.org/download.html](https://ffmpeg.org/download.html)
(the Windows builds include `ffprobe.exe`).

If `ffprobe.exe` is not bundled, the app still works -- ffprobe features
will simply require the user to have ffmpeg installed and on their PATH.

### Build

```bash
build_windows.bat
```

Or run directly:

```bash
pyinstaller app.spec
```

### Output

The executable is generated at:

```
dist\RNMR.exe
```

### Notes

- **No Python required** on the target machine.
- **TMDB API key**: Users must provide their own API key via the
  Settings dialog or a `TMDB_API_KEY` environment variable.
  Get a free key at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api).
- **ffprobe**: Bundled inside the executable when `resources/ffprobe.exe`
  is present at build time. Otherwise falls back to system PATH.
  ffprobe is part of the [FFmpeg](https://ffmpeg.org/) project and is
  licensed under the LGPL v2.1+. See `LICENSE_FFMPEG.txt` for details.
- The build uses `--onefile` and `--windowed` mode (no console window).

## Safety Features

- **No overwrites**: Skips if destination file exists
- **Error isolation**: Single file failures don't stop the batch
- **Dry-run mode**: Always preview before renaming
- **Confirmation prompt**: Optional confirmation before execution

## Project Structure

```
renamer/
  renamer.py              # CLI entrypoint
  parser.py               # Filename parsing + subtitle detection
  tmdb.py                 # TMDB API client with scoring/candidates
  formatter.py            # Output formatting
  cache.py                # Local JSON cache
  models.py               # Data classes
  id_mapping.py           # Manual TMDB ID disambiguation
  detection.py            # Detection state machine (DetectionController)
  history.py              # SQLite-backed persistent rename history
  metadata_extractor.py   # ffprobe metadata extraction
  runtime.py              # PyInstaller path resolution & ffprobe detection
  cleaner.py              # Title cleaning for TMDB search queries

gui/
  main.py                 # GUI entry point
  main_window.py          # Main application window
  worker.py               # Background workers for scanning/renaming
  theme.py                # Dark theme stylesheet
  settings.py             # Settings persistence
  settings_dialog.py      # Settings dialog with behavior/template tabs
  setup_wizard.py         # First-run TMDB API key wizard
  tmdb_select_dialog.py   # Interactive TMDB match selection with search
  media_type_dialog.py    # Media type confirmation dialog
  failed_lookup_dialog.py # Fallback dialog for unresolved titles
  search_dialog.py        # Manual TMDB search dialog
  id_dialog.py            # TMDB ID disambiguation dialog
```

## Support RNMR

If you find RNMR useful and would like to support its development:

**Buy Me a Coffee**

[buymeacoffee.com/rnmr](https://buymeacoffee.com/rnmr)

**USDT (TRC20 Network)**

```
TKy1aQvUbmFqVnvAgiVSE9X1g3QYogWkH9
```

> Please make sure to use the **TRC20 network** when sending USDT. Crypto transactions are non-refundable.

## License

MIT
