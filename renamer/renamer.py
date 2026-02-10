#!/usr/bin/env python3
"""
RNMR - Media File Renamer

A CLI tool for renaming media files using TMDB metadata.
"""
import argparse
import os
import sys
from pathlib import Path

from .parser import parse_filename, is_media_file
from .tmdb import TMDBClient
from .formatter import (
    format_series_name,
    format_movie_name,
    format_fallback,
    get_new_path,
    filenames_match
)
from .cache import Cache
from .models import RenameResult, ParsedMedia


def print_diff(old_name: str, new_name: str, is_skip: bool = False) -> None:
    """Print the rename diff."""
    if is_skip:
        print(f"  [SKIP] {old_name}")
    else:
        print(f"  {old_name}")
        print(f"    -> {new_name}")


def interactive_select(results: list[dict], title: str) -> int | None:
    """
    Interactive selection for ambiguous TMDB matches.

    Args:
        results: List of search results
        title: The title being searched

    Returns:
        Selected index or None to skip
    """
    print(f"\nMultiple matches found for '{title}':")
    print("-" * 50)

    for i, result in enumerate(results[:10], 1):  # Limit to 10 results
        name = result.get("title") or result.get("name", "Unknown")
        original = result.get("original_title") or result.get("original_name", "")
        date = result.get("release_date") or result.get("first_air_date", "")
        year = date[:4] if date else "????"

        if original and original != name:
            print(f"  {i}. {name} ({year}) - Original: {original}")
        else:
            print(f"  {i}. {name} ({year})")

    print("  0. Skip this file")
    print()

    while True:
        try:
            choice = input("Select [1]: ").strip()
            if not choice:
                return 0  # Default to first result
            choice = int(choice)
            if choice == 0:
                return None
            if 1 <= choice <= min(10, len(results)):
                return choice - 1
        except ValueError:
            pass
        print("Invalid choice. Try again.")


def process_file(
    filepath: Path,
    tmdb_client: TMDBClient | None,
    dry_run: bool = True,
    keep_year: bool = True,
    include_episode_title: bool = True
) -> RenameResult:
    """
    Process a single media file.

    Args:
        filepath: Path to the file
        tmdb_client: TMDB client (None to skip TMDB)
        dry_run: If True, don't actually rename
        keep_year: Include year in movie names
        include_episode_title: Include episode title for series

    Returns:
        RenameResult with operation details
    """
    # Parse the filename
    parsed = parse_filename(filepath)
    extension = filepath.suffix

    new_filename = None

    # Try TMDB lookup
    if tmdb_client:
        try:
            if parsed.media_type == "series":
                series = tmdb_client.search_series(parsed.title_guess)
                if series and parsed.season is not None:
                    # Get episode details
                    episode_details = []
                    for ep_num in parsed.episodes:
                        ep = tmdb_client.get_episode_details(
                            series.id, parsed.season, ep_num
                        )
                        if ep:
                            episode_details.append(ep)

                    new_filename = format_series_name(
                        series,
                        parsed.season,
                        parsed.episodes,
                        episode_details if episode_details else None,
                        extension,
                        include_episode_title
                    )
            else:  # movie
                movie = tmdb_client.search_movie(parsed.title_guess, parsed.year)
                if movie:
                    new_filename = format_movie_name(movie, extension, keep_year)

        except Exception as e:
            # Log error but continue with fallback
            print(f"  [WARN] TMDB error for {filepath.name}: {e}")

    # Fallback if TMDB didn't work
    if not new_filename:
        new_filename = format_fallback(parsed, extension)

    new_path = get_new_path(filepath, new_filename)

    # Check if already named correctly
    if filenames_match(filepath.name, new_filename):
        return RenameResult(
            original_path=str(filepath),
            new_path=str(new_path),
            success=True,
            skipped=True,
            skip_reason="Already named correctly"
        )

    # Check for duplicate
    if new_path.exists() and new_path != filepath:
        return RenameResult(
            original_path=str(filepath),
            new_path=str(new_path),
            success=False,
            error="Destination file already exists",
            skipped=True,
            skip_reason="Duplicate file exists"
        )

    # Perform rename if not dry run
    if not dry_run:
        try:
            filepath.rename(new_path)
        except OSError as e:
            return RenameResult(
                original_path=str(filepath),
                new_path=str(new_path),
                success=False,
                error=str(e)
            )

    return RenameResult(
        original_path=str(filepath),
        new_path=str(new_path),
        success=True
    )


def find_media_files(path: Path, recursive: bool = False) -> list[Path]:
    """
    Find all media files in a directory.

    Args:
        path: Directory or file path
        recursive: Whether to search recursively

    Returns:
        List of media file paths
    """
    if path.is_file():
        if is_media_file(path):
            return [path]
        return []

    if not path.is_dir():
        return []

    files = []
    if recursive:
        for item in path.rglob("*"):
            if item.is_file() and is_media_file(item):
                files.append(item)
    else:
        for item in path.iterdir():
            if item.is_file() and is_media_file(item):
                files.append(item)

    return sorted(files)


def main(args: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="renamer",
        description="Rename media files using TMDB metadata."
    )

    parser.add_argument(
        "path",
        type=Path,
        help="File or directory to process"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be renamed without actually renaming"
    )
    parser.add_argument(
        "--recursive", "-r",
        action="store_true",
        help="Process directories recursively"
    )
    parser.add_argument(
        "--use-tmdb",
        action="store_true",
        help="Use TMDB for metadata lookup"
    )
    parser.add_argument(
        "--keep-year",
        action="store_true",
        default=True,
        help="Include year in movie names (default: True)"
    )
    parser.add_argument(
        "--no-year",
        action="store_true",
        help="Don't include year in movie names"
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Interactively choose from multiple TMDB matches"
    )
    parser.add_argument(
        "--no-episode-title",
        action="store_true",
        help="Don't include episode title in series filenames"
    )
    parser.add_argument(
        "--language",
        type=str,
        default="es-MX",
        help="Language for TMDB results (default: es-MX)"
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Directory for cache file (default: current directory)"
    )

    parsed_args = parser.parse_args(args)

    # Validate path
    if not parsed_args.path.exists():
        print(f"Error: Path does not exist: {parsed_args.path}")
        return 1

    # Handle year flag conflict
    keep_year = parsed_args.keep_year and not parsed_args.no_year

    # Setup TMDB client if needed
    tmdb_client = None
    if parsed_args.use_tmdb:
        api_key = os.environ.get("TMDB_API_KEY")
        if not api_key:
            print("Error: TMDB_API_KEY environment variable not set.")
            print("Set it with: export TMDB_API_KEY=your_key_here")
            return 1

        cache = Cache(parsed_args.cache_dir)
        interactive_cb = interactive_select if parsed_args.interactive else None
        tmdb_client = TMDBClient(
            api_key=api_key,
            cache=cache,
            language=parsed_args.language,
            interactive_callback=interactive_cb
        )

    # Find media files
    files = find_media_files(parsed_args.path, parsed_args.recursive)
    if not files:
        print("No media files found.")
        return 0

    print(f"Found {len(files)} media file(s)")
    if parsed_args.dry_run:
        print("[DRY RUN - no files will be renamed]\n")
    else:
        print()

    # Process files
    results = []
    renamed_count = 0
    skipped_count = 0
    error_count = 0

    for filepath in files:
        result = process_file(
            filepath,
            tmdb_client,
            dry_run=parsed_args.dry_run,
            keep_year=keep_year,
            include_episode_title=not parsed_args.no_episode_title
        )
        results.append(result)

        old_name = Path(result.original_path).name
        new_name = Path(result.new_path).name

        if result.skipped:
            skipped_count += 1
            print_diff(old_name, new_name, is_skip=True)
            if result.skip_reason:
                print(f"       Reason: {result.skip_reason}")
        elif result.success:
            renamed_count += 1
            print_diff(old_name, new_name)
        else:
            error_count += 1
            print(f"  [ERROR] {old_name}")
            print(f"          {result.error}")

    # Summary
    print()
    print("-" * 50)
    action = "Would rename" if parsed_args.dry_run else "Renamed"
    print(f"{action}: {renamed_count} | Skipped: {skipped_count} | Errors: {error_count}")

    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
