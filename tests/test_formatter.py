"""Tests for renamer.formatter, including filename-safety guarantees."""
from pathlib import Path

import pytest

from renamer.formatter import (
    sanitize_filename, format_series_name, format_movie_name,
    format_fallback, get_new_path, render_template,
)
from renamer.models import TMDBSeries, TMDBMovie, TMDBEpisode, ParsedMedia


def test_sanitize_strips_illegal_chars():
    out = sanitize_filename('a/b\\c:d*e?f"g<h>i|j')
    for ch in '/\\:*?"<>|':
        assert ch not in out


def test_path_traversal_via_episode_title_is_neutralised():
    # SECURITY: a malicious TMDB episode title must not escape the directory.
    ep = TMDBEpisode(1, 1, 1, name="../../../etc/passwd")
    series = TMDBSeries(1, "Show", "Show", 2020)
    fn = format_series_name(series, 1, [1], [ep], ".mkv", True)
    assert "/" not in fn
    assert "\\" not in fn
    base = Path("/media/shows")
    new_path = get_new_path(base / "orig.mkv", fn)
    assert new_path.parent == base


def test_series_name_with_episode_title():
    series = TMDBSeries(1, "Breaking Bad", "Breaking Bad", 2008)
    ep = TMDBEpisode(1, 1, 4, name="Cancer Man")
    fn = format_series_name(series, 1, [4], [ep], ".mkv", True)
    assert fn == "Breaking Bad - S01E04 - Cancer Man.mkv"


def test_multi_episode_omits_title():
    series = TMDBSeries(1, "Show", "Show", 2020)
    fn = format_series_name(series, 2, [5, 6], None, ".mkv", True)
    assert fn == "Show - S02E05E06.mkv"


def test_movie_name_with_and_without_year():
    m = TMDBMovie(1, "Inception", "Inception", 2010)
    assert format_movie_name(m, ".mkv", True) == "Inception (2010).mkv"
    assert format_movie_name(m, ".mkv", False) == "Inception.mkv"


def test_original_title_priority():
    m = TMDBMovie(1, "Localized", "OriginalName", 2010)
    assert format_movie_name(m, ".mkv", True).startswith("OriginalName")


def test_render_template_missing_var_raises():
    with pytest.raises(KeyError):
        render_template("{title} {nonexistent}", {"title": "X"})


def test_fallback_without_tmdb():
    p = ParsedMedia(
        raw_name="x", title_guess="My Show", media_type="series",
        season=1, episodes=[2],
    )
    assert format_fallback(p, ".mkv") == "My Show - S01E02.mkv"
