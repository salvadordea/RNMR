#!/usr/bin/env python3
"""
RNMR - Media File Renamer

A CLI tool for renaming media files using TMDB metadata.
"""
import argparse
import sys
from pathlib import Path

from .parser import parse_filename, is_media_file, find_associated_subtitles
from .tmdb import TMDBClient, TMDBError
from .formatter import (
    format_series_name,
    format_movie_name,
    format_fallback,
    format_subtitle_name,
    get_new_path,
    filenames_match
)
from .cache import Cache
from .models import RenameResult, SubtitleFile

# Global verbose flag
VERBOSE = False


def log_verbose(message: str) -> None:
    """Print message if verbose mode is enabled."""
    if VERBOSE:
        print(f"  [DEBUG] {message}")


def print_video_diff(old_name: str, new_name: str) -> None:
    """Print the video rename diff."""
    print(f"Video:")
    print(f"  {old_name}")
    print(f"  -> {new_name}")


def print_subtitle_diff(old_name: str, new_name: str) -> None:
    """Print the subtitle rename diff."""
    print(f"Subtitle:")
    print(f"  {old_name}")
    print(f"  -> {new_name}")


def print_skip(old_name: str, reason: str, file_type: str = "Video") -> None:
    """Print skip message."""
    print(f"{file_type}:")
    print(f"  [SKIP] {old_name}")
    print(f"         Reason: {reason}")


def print_error(old_name: str, error: str, file_type: str = "Video") -> None:
    """Print error message."""
    print(f"{file_type}:")
    print(f"  [ERROR] {old_name}")
    print(f"          {error}")


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


def rename_file(source: Path, dest: Path, dry_run: bool) -> tuple[bool, str | None]:
    """
    Rename a file safely.

    Args:
        source: Source path
        dest: Destination path
        dry_run: If True, don't actually rename

    Returns:
        Tuple of (success, error_message)
    """
    # Check if destination already exists (and is not the same file)
    if dest.exists() and source.resolve() != dest.resolve():
        return False, "Destination file already exists"

    if not dry_run:
        try:
            source.rename(dest)
        except OSError as e:
            return False, str(e)

    return True, None


def process_subtitles(
    video_path: Path,
    new_video_basename: str,
    subtitles: list[SubtitleFile],
    dry_run: bool
) -> list[RenameResult]:
    """
    Process and rename subtitles associated with a video.

    Args:
        video_path: Original video path
        new_video_basename: New video filename without extension
        subtitles: List of associated subtitles
        dry_run: If True, don't actually rename

    Returns:
        List of RenameResult for each subtitle
    """
    results = []

    for sub in subtitles:
        sub_path = Path(sub.path)
        new_sub_name = format_subtitle_name(new_video_basename, sub)
        new_sub_path = sub_path.parent / new_sub_name

        # Check if already named correctly
        if filenames_match(sub_path.name, new_sub_name):
            results.append(RenameResult(
                original_path=str(sub_path),
                new_path=str(new_sub_path),
                success=True,
                skipped=True,
                skip_reason="Already named correctly",
                file_type="subtitle"
            ))
            continue

        success, error = rename_file(sub_path, new_sub_path, dry_run)

        if error:
            results.append(RenameResult(
                original_path=str(sub_path),
                new_path=str(new_sub_path),
                success=False,
                error=error,
                skipped=True,
                skip_reason=error,
                file_type="subtitle"
            ))
        else:
            results.append(RenameResult(
                original_path=str(sub_path),
                new_path=str(new_sub_path),
                success=True,
                file_type="subtitle"
            ))

    return results


def process_file(
    filepath: Path,
    tmdb_client: TMDBClient | None,
    dry_run: bool = True,
    keep_year: bool = True,
    include_episode_title: bool = True
) -> tuple[RenameResult, list[RenameResult]]:
    """
    Process a single media file and its associated subtitles.

    Args:
        filepath: Path to the file
        tmdb_client: TMDB client (None to skip TMDB)
        dry_run: If True, don't actually rename
        keep_year: Include year in movie names
        include_episode_title: Include episode title for series

    Returns:
        Tuple of (video_result, subtitle_results)
    """
    # Parse the filename
    parsed = parse_filename(filepath)
    extension = filepath.suffix

    log_verbose(f"Parsed: title='{parsed.title_guess}', type={parsed.media_type}, "
                f"season={parsed.season}, episodes={parsed.episodes}")

    new_filename = None

    # Try TMDB lookup
    if tmdb_client:
        try:
            if parsed.media_type == "series":
                log_verbose(f"Searching TMDB for series: '{parsed.title_guess}'")
                series = tmdb_client.search_series(parsed.title_guess)
                if series:
                    log_verbose(f"TMDB found: id={series.id}, name='{series.name}', "
                                f"original='{series.original_name}'")
                    if parsed.season is not None:
                        # Get episode details (only for single episodes when needed)
                        episode_details = []
                        if include_episode_title and len(parsed.episodes) == 1:
                            for ep_num in parsed.episodes:
                                log_verbose(f"Fetching episode S{parsed.season:02d}E{ep_num:02d}")
                                ep = tmdb_client.get_episode_details(
                                    series.id, parsed.season, ep_num
                                )
                                if ep:
                                    log_verbose(f"Episode title: '{ep.name}'")
                                    episode_details.append(ep)
                                else:
                                    log_verbose("Episode not found in TMDB")

                        new_filename = format_series_name(
                            series,
                            parsed.season,
                            parsed.episodes,
                            episode_details if episode_details else None,
                            extension,
                            include_episode_title
                        )
                else:
                    log_verbose("TMDB search returned no results")
            else:  # movie
                log_verbose(f"Searching TMDB for movie: '{parsed.title_guess}' year={parsed.year}")
                movie = tmdb_client.search_movie(parsed.title_guess, parsed.year)
                if movie:
                    log_verbose(f"TMDB found: id={movie.id}, title='{movie.title}', "
                                f"original='{movie.original_title}'")
                    new_filename = format_movie_name(movie, extension, keep_year)
                else:
                    log_verbose("TMDB search returned no results")

        except Exception as e:
            # Log error but continue with fallback
            print(f"  [WARN] TMDB error for {filepath.name}: {e}")

    # Fallback if TMDB didn't work
    if not new_filename:
        new_filename = format_fallback(parsed, extension)

    new_path = get_new_path(filepath, new_filename)

    # Find associated subtitles BEFORE checking if video needs renaming
    subtitles = find_associated_subtitles(filepath)

    # Get new basename for subtitles (without video extension)
    new_basename = Path(new_filename).stem

    # Check if video already named correctly
    if filenames_match(filepath.name, new_filename):
        video_result = RenameResult(
            original_path=str(filepath),
            new_path=str(new_path),
            success=True,
            skipped=True,
            skip_reason="Already named correctly",
            file_type="video"
        )
        # Still process subtitles even if video is already named correctly
        subtitle_results = process_subtitles(filepath, new_basename, subtitles, dry_run)
        return video_result, subtitle_results

    # Rename video
    success, error = rename_file(filepath, new_path, dry_run)

    if error:
        video_result = RenameResult(
            original_path=str(filepath),
            new_path=str(new_path),
            success=False,
            error=error,
            skipped=True,
            skip_reason=error,
            file_type="video"
        )
        # Don't rename subtitles if video rename failed
        return video_result, []

    video_result = RenameResult(
        original_path=str(filepath),
        new_path=str(new_path),
        success=True,
        file_type="video"
    )

    # Process subtitles
    subtitle_results = process_subtitles(filepath, new_basename, subtitles, dry_run)

    return video_result, subtitle_results


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


def confirm_proceed(count: int) -> bool:
    """
    Ask user to confirm proceeding with rename.

    Args:
        count: Number of files to rename

    Returns:
        True if user confirms, False otherwise
    """
    while True:
        response = input(f"\nProceed with renaming {count} files? (y/n): ").strip().lower()
        if response in ('y', 'yes'):
            return True
        if response in ('n', 'no'):
            return False
        print("Please enter 'y' or 'n'.")


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
        "--confirm",
        action="store_true",
        help="Ask for confirmation before renaming"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Limit number of files to process"
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
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed debug information"
    )

    parsed_args = parser.parse_args(args)

    # Set global verbose flag
    global VERBOSE
    VERBOSE = parsed_args.verbose

    # Validate path
    if not parsed_args.path.exists():
        print(f"Error: Path does not exist: {parsed_args.path}")
        return 1

    # Handle year flag conflict
    keep_year = parsed_args.keep_year and not parsed_args.no_year

    # Setup TMDB client if needed
    tmdb_client = None
    if parsed_args.use_tmdb:
        try:
            cache = Cache(parsed_args.cache_dir)
            interactive_cb = interactive_select if parsed_args.interactive else None
            tmdb_client = TMDBClient(
                cache=cache,
                language=parsed_args.language,
                interactive_callback=interactive_cb,
                verbose=VERBOSE
            )
        except TMDBError as e:
            print(f"Error: {e}")
            return 1

    # Find media files
    files = find_media_files(parsed_args.path, parsed_args.recursive)
    if not files:
        print("No media files found.")
        return 0

    # Apply limit if specified
    if parsed_args.limit and parsed_args.limit > 0:
        files = files[:parsed_args.limit]

    print(f"Found {len(files)} media file(s)")
    if parsed_args.dry_run:
        print("[DRY RUN - no files will be renamed]\n")
    else:
        print()

    # First pass: collect all rename operations for preview
    all_operations: list[tuple[RenameResult, list[RenameResult]]] = []

    for filepath in files:
        video_result, subtitle_results = process_file(
            filepath,
            tmdb_client,
            dry_run=True,  # Always dry-run first for preview
            keep_year=keep_year,
            include_episode_title=not parsed_args.no_episode_title
        )
        all_operations.append((video_result, subtitle_results))

    # Display preview
    rename_count = 0
    for video_result, subtitle_results in all_operations:
        video_old = Path(video_result.original_path).name
        video_new = Path(video_result.new_path).name

        if video_result.skipped:
            if video_result.skip_reason != "Already named correctly":
                print_skip(video_old, video_result.skip_reason or "Unknown", "Video")
        elif video_result.success:
            print_video_diff(video_old, video_new)
            rename_count += 1
        else:
            print_error(video_old, video_result.error or "Unknown error", "Video")

        # Show subtitle operations
        for sub_result in subtitle_results:
            sub_old = Path(sub_result.original_path).name
            sub_new = Path(sub_result.new_path).name

            if sub_result.skipped:
                if sub_result.skip_reason != "Already named correctly":
                    print_skip(sub_old, sub_result.skip_reason or "Unknown", "Subtitle")
            elif sub_result.success:
                print_subtitle_diff(sub_old, sub_new)
                rename_count += 1
            else:
                print_error(sub_old, sub_result.error or "Unknown error", "Subtitle")

        print()  # Blank line between files

    # If dry run, show summary and exit
    if parsed_args.dry_run:
        print("-" * 50)
        print(f"Would rename: {rename_count} files")
        return 0

    # If no files to rename, exit
    if rename_count == 0:
        print("-" * 50)
        print("No files to rename.")
        return 0

    # Ask for confirmation if --confirm is set
    if parsed_args.confirm:
        if not confirm_proceed(rename_count):
            print("Cancelled.")
            return 0

    # Second pass: actually perform renames
    print("\nRenaming files...")
    print("-" * 50)

    renamed_count = 0
    skipped_count = 0
    error_count = 0

    for filepath in files:
        video_result, subtitle_results = process_file(
            filepath,
            tmdb_client,
            dry_run=False,  # Actually rename
            keep_year=keep_year,
            include_episode_title=not parsed_args.no_episode_title
        )

        # Count video result
        if video_result.skipped:
            skipped_count += 1
        elif video_result.success:
            renamed_count += 1
        else:
            error_count += 1

        # Count subtitle results
        for sub_result in subtitle_results:
            if sub_result.skipped:
                skipped_count += 1
            elif sub_result.success:
                renamed_count += 1
            else:
                error_count += 1

    # Summary
    print()
    print("-" * 50)
    print(f"Renamed: {renamed_count} | Skipped: {skipped_count} | Errors: {error_count}")

    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
