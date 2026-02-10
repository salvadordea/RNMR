# RNMR - Media File Renamer

A CLI tool for renaming media files (movies and TV series) using TMDB metadata.

## Features

- Automatic detection of movies and TV series
- Episode pattern recognition (S01E04, 1x04, S01E04E05, etc.)
- TMDB integration for official titles and episode names
- Local caching to minimize API calls
- Smart title matching using similarity scoring
- Interactive mode for ambiguous matches
- Dry-run mode for safe previewing
- Recursive directory processing
- Spanish language support (configurable)

## Requirements

- Python 3.10+
- TMDB API key (free at https://www.themoviedb.org/settings/api)

## Installation

```bash
git clone https://github.com/yourusername/RNMR.git
cd RNMR
pip install -e .
```

Or install dependencies directly:

```bash
pip install -r requirements.txt
```

## Configuration

Set your TMDB API key as an environment variable:

```bash
# Linux/macOS
export TMDB_API_KEY=your_key_here

# Windows (PowerShell)
$env:TMDB_API_KEY="your_key_here"

# Windows (CMD)
set TMDB_API_KEY=your_key_here
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
```

### Output Format

**Series:**
```
{Official Series Title} - S{season:02}E{episode:02} - {Episode Name}.ext
```
Example: `Breaking Bad - S01E01 - Pilot.mkv`

Multi-episode: `Breaking Bad - S01E04E05 - Gray Matter.mkv`

**Movies:**
```
{Official Title} ({Year}).ext
```
Example: `The Matrix (1999).mkv`

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

The tool creates a `.renamer_cache.json` file to store TMDB lookups, avoiding repeated API calls for:
- Title to TMDB ID mappings
- Movie search results
- Series search results
- Episode details

## Project Structure

```
renamer/
  renamer.py     # CLI entrypoint
  parser.py      # Filename parsing
  tmdb.py        # TMDB API client
  formatter.py   # Output formatting
  cache.py       # Local JSON cache
  models.py      # Data classes
```

## License

MIT
