"""Tests for renamer.cache, including the language-aware episode key."""
from renamer.cache import Cache

EP = {"series_id": 1, "season_number": 1, "episode_number": 1,
      "name": "Pilot", "overview": ""}


def test_series_search_roundtrip_and_persistence(tmp_cache_dir):
    c = Cache(tmp_cache_dir)
    c.set_series_search("dark", {
        "id": 1, "name": "Dark", "original_name": "Dark",
        "first_air_year": 2017, "overview": "", "original_language": "de",
    })
    # Reload from disk; keys are case-insensitive.
    assert Cache(tmp_cache_dir).get_series_search("DARK")["id"] == 1


def test_deferred_save_then_flush(tmp_cache_dir):
    c = Cache(tmp_cache_dir)
    c.set_episode(1, 1, 1, EP, save=False)
    # Not flushed: a fresh load must NOT see it yet.
    assert Cache(tmp_cache_dir).get_episode(1, 1, 1) is None
    c.flush()
    assert Cache(tmp_cache_dir).get_episode(1, 1, 1)["name"] == "Pilot"


def test_corrupt_cache_file_is_tolerated(tmp_cache_dir):
    (tmp_cache_dir / ".renamer_cache.json").write_text("{ not json")
    c = Cache(tmp_cache_dir)  # must not raise
    assert c.get_series_search("x") is None


def test_batch_mode_defers_writes_until_end(tmp_cache_dir):
    # Performance fix: a whole scan should write the file once, not per lookup.
    c = Cache(tmp_cache_dir)
    c.begin_batch()
    c.set_title_id("breaking bad", "series", 1396)
    c.set_episode(1, 1, 1, EP)
    # Nothing persisted yet while the batch is open.
    assert Cache(tmp_cache_dir).get_title_id("breaking bad", "series") is None
    c.end_batch()
    # One flush at the end persists everything.
    reloaded = Cache(tmp_cache_dir)
    assert reloaded.get_title_id("breaking bad", "series") == 1396
    assert reloaded.get_episode(1, 1, 1)["name"] == "Pilot"


def test_episode_cache_is_language_aware(tmp_cache_dir):
    # BUG-03 regression: a title cached in one language must not be
    # returned when another language is requested.
    c = Cache(tmp_cache_dir)
    c.set_episode(1, 1, 1, {**EP, "name": "Pilot"}, language="en-US")
    c.set_episode(1, 1, 1, {**EP, "name": "Piloto"}, language="es-ES")
    assert c.get_episode(1, 1, 1, language="en-US")["name"] == "Pilot"
    assert c.get_episode(1, 1, 1, language="es-ES")["name"] == "Piloto"
    # A language with no cached entry misses (re-fetch path).
    assert c.get_episode(1, 1, 1, language="ja-JP") is None
