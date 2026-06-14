"""Tests for renamer.parser filename parsing."""
from pathlib import Path

from renamer.parser import parse_filename, is_media_file, is_subtitle_file


def test_sxxexx_with_noise():
    p = parse_filename("Breaking.Bad.S01E04.1080p.x264.mkv")
    assert p.media_type == "series"
    assert p.season == 1
    assert p.episodes == [4]
    assert p.title_guess == "Breaking Bad"


def test_1xnn_pattern():
    p = parse_filename("Friends 1x07 The One.mkv")
    assert p.season == 1
    assert p.episodes == [7]


def test_multi_episode():
    p = parse_filename("Show.S02E05E06.mkv")
    assert p.season == 2
    assert p.episodes == [5, 6]


def test_season_episode_words():
    p = parse_filename("The Office Season 3 Episode 6.mkv")
    assert p.season == 3
    assert p.episodes == [6]


def test_movie_with_year_and_noise():
    p = parse_filename("Inception.2010.1080p.BluRay.mkv")
    assert p.media_type == "movie"
    assert p.year == 2010
    assert p.title_guess == "Inception"


def test_title_guess_never_empty():
    p = parse_filename("S01E01.mkv")
    assert p.title_guess  # falls back to raw name


def test_media_extension_detection():
    assert is_media_file(Path("a.mkv"))
    assert is_media_file(Path("a.MP4"))
    assert not is_media_file(Path("a.txt"))


def test_subtitle_extension_detection():
    assert is_subtitle_file(Path("a.srt"))
    assert is_subtitle_file(Path("a.en.srt"))
    assert not is_subtitle_file(Path("a.mkv"))
