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
from gui.worker import ScanWorker, DuplicateScanWorker


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


# -- Progressive scan output (no network: use_tmdb=False) -------------------

def test_run_emits_every_file_grouped(tmp_path):
    # Two series + one movie; files created on disk, no TMDB.
    names = [
        "Breaking.Bad.S01E01.mkv", "Breaking.Bad.S01E02.mkv",
        "Dark.S01E01.mkv", "Inception.2010.mkv",
    ]
    for n in names:
        (tmp_path / n).touch()

    w = ScanWorker(folder_path=str(tmp_path), recursive=False,
                   use_tmdb=False, include_episode_title=True)
    seen = []
    w.item_found.connect(lambda row, item: seen.append((row, item)))
    w.run()

    assert len(seen) == len(names)
    # Rows are emitted as a dense 0..N-1 sequence (GUI appends in order).
    assert [row for row, _ in seen] == list(range(len(names)))
    # Files of the same series are emitted contiguously (grouped).
    emitted_names = [item.original_path.name for _, item in seen]
    bb = [i for i, n in enumerate(emitted_names) if n.startswith("Breaking")]
    assert bb == [bb[0], bb[0] + 1]


# -- Duplicate finder hashing (#5) ------------------------------------------

def test_hash_helpers_are_consistent(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"hello world" * 1000)
    assert DuplicateScanWorker._hash_full(f) == DuplicateScanWorker._hash_full(f)
    assert DuplicateScanWorker._hash_quick(f) == DuplicateScanWorker._hash_quick(f)


def test_name_duplicates_do_not_full_hash(tmp_path):
    # Same normalized name, DIFFERENT size -> not exact dupes, so they fall
    # into the name-duplicate path, which must NOT read whole files.
    (tmp_path / "Movie.1080p.x264.mkv").write_bytes(b"a" * 100)
    (tmp_path / "Movie.720p.x265.mkv").write_bytes(b"b" * 200)

    w = DuplicateScanWorker(folder_path=str(tmp_path), recursive=False)
    # Make full hashing blow up; name-group detection must still succeed.
    w._hash_full = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("name dupes must not full-hash"))

    captured = []
    w.finished.connect(lambda groups: captured.append(groups))
    w.run()

    assert captured, "finished should emit"
    groups = captured[0]
    name_groups = [g for g in groups if g["group_type"] == "name"]
    assert len(name_groups) == 1
    assert len(name_groups[0]["items"]) == 2
