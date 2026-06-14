"""Regression tests for the two scan bugs fixed in this branch.

BUG-01: series scans fetched one HTTP request per episode (very slow).
BUG-02: inconsistent filenames split one series into several prompts.
"""
from pathlib import Path

from renamer.cache import Cache
from renamer.tmdb import TMDBClient
from renamer.parser import parse_filename
from renamer.detection import BatchContext
from renamer.models import TMDBSeries
from gui.worker import ScanWorker


def _season_resp(n=12):
    return {"episodes": [{"episode_number": i, "name": f"Ep {i}"}
                         for i in range(1, n + 1)]}


# -- BUG-02: grouping -------------------------------------------------------

def test_inconsistent_names_collapse_to_one_group():
    names = ["The.Mandalorian.2019.S01E01.mkv",
             "The.Mandalorian.S01E02.mkv",
             "The Mandalorian S01E03.mkv"]
    keys = {ScanWorker._group_key(parse_filename(n)) for n in names}
    assert keys == {"the mandalorian"}


def test_same_title_different_year_movies_stay_separate():
    k1 = ScanWorker._group_key(parse_filename("Dune.2021.mkv"))
    k2 = ScanWorker._group_key(parse_filename("Dune.1984.mkv"))
    assert k1 != k2


# -- BUG-01: episode prefetch ----------------------------------------------

def _worker(folder):
    return ScanWorker(folder_path=folder, recursive=False, use_tmdb=True,
                      include_episode_title=True)


def test_prefetch_one_request_per_season(tmp_cache_dir):
    c = TMDBClient(api_key="x", cache=Cache(tmp_cache_dir))
    calls = []

    def fake(e, params=None, retries=3):
        calls.append(e)
        return _season_resp(12)

    c._request = fake
    w = _worker(str(tmp_cache_dir))
    files = ([f"Show.S01E{i:02d}.mkv" for i in range(1, 13)] +
             [f"Show.S02E{i:02d}.mkv" for i in range(1, 4)])
    entries = [(Path(f), parse_filename(f)) for f in files]
    ctx = BatchContext(series=TMDBSeries(99, "Show", "Show", 2020))
    w._prefetch_episodes(ctx, entries, c)
    assert len(calls) == 2  # one per season, not per episode
    assert len(ctx.episode_cache) == 15


def test_repeat_scan_served_from_cache(tmp_cache_dir):
    c = TMDBClient(api_key="x", cache=Cache(tmp_cache_dir))
    c._request = lambda e, params=None, retries=3: _season_resp(12)
    w = _worker(str(tmp_cache_dir))
    files = [f"Show.S01E{i:02d}.mkv" for i in range(1, 13)]
    entries = [(Path(f), parse_filename(f)) for f in files]
    ctx = BatchContext(series=TMDBSeries(99, "Show", "Show", 2020))
    w._prefetch_episodes(ctx, entries, c)  # warms cache

    def boom(*a, **k):
        raise AssertionError("network hit on repeat scan")

    c._request = boom
    ctx2 = BatchContext(series=TMDBSeries(99, "Show", "Show", 2020))
    w._prefetch_episodes(ctx2, entries, c)
    assert len(ctx2.episode_cache) == 12
