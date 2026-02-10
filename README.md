# RNMR - Media File Renamer

A CLI tool for renaming media files (movies and TV series) using TMDB metadata.

## Features

- Automatic detection of movies and TV series
- Episode pattern recognition (S01E04, 1x04, S01E04E05, etc.)
- TMDB integration for official titles and episode names
- **Original title priority** - uses original language titles by default
- **Subtitle support** - automatically renames associated .srt files
- Local caching to minimize API calls
- Smart title matching using similarity scoring
- Interactive mode for ambiguous matches
- Dry-run mode for safe previewing
- Confirmation prompt before renaming
- File limit for batch processing
- Recursive directory processing

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

## Safety Features

- **No overwrites**: Skips if destination file exists
- **Error isolation**: Single file failures don't stop the batch
- **Dry-run mode**: Always preview before renaming
- **Confirmation prompt**: Optional confirmation before execution

## Project Structure

```
renamer/
  renamer.py     # CLI entrypoint
  parser.py      # Filename parsing + subtitle detection
  tmdb.py        # TMDB API client
  formatter.py   # Output formatting
  cache.py       # Local JSON cache
  models.py      # Data classes
```

## License

MIT
