"""Tests for the detection state machine (network mocked)."""
from pathlib import Path

from renamer.cache import Cache
from renamer.tmdb import TMDBClient
from renamer.parser import parse_filename
from renamer.detection import DetectionController, DetectionState, Action
from renamer.id_mapping import IDMapping


def _controller(client, cache_dir):
    return DetectionController(
        client, IDMapping(cache_dir),
        settings={"always_ask_media_type": False,
                  "always_confirm_tmdb": False,
                  "interactive_fallback": False},
    )


def _drive(ctrl, batch, stop_actions):
    """Step the machine until a stop action or DONE; return actions seen."""
    seen = []
    for _ in range(20):
        a = ctrl.step(batch)
        seen.append(a)
        if a in stop_actions or a == Action.DONE:
            break
        if a == Action.CONTINUE:
            continue
        break
    return seen


def test_single_result_auto_confirms(tmp_cache_dir):
    c = TMDBClient(api_key="x", cache=Cache(tmp_cache_dir))
    c._request = lambda e, params=None, retries=3: {"results": [
        {"id": 1396, "name": "Breaking Bad", "original_name": "Breaking Bad",
         "first_air_date": "2008-01-20", "popularity": 99}]}
    ctrl = _controller(c, tmp_cache_dir)
    p = parse_filename("Breaking.Bad.S01E01.mkv")
    batch = ctrl.create_batch("breaking bad",
                              [(Path("Breaking.Bad.S01E01.mkv"), p)], "en-US")
    _drive(ctrl, batch, {Action.DONE})
    assert batch.state == DetectionState.CONFIRMED
    assert batch.series is not None
    assert batch.series.id == 1396


def test_multiple_results_request_selection(tmp_cache_dir):
    c = TMDBClient(api_key="x", cache=Cache(tmp_cache_dir))
    c._request = lambda e, params=None, retries=3: {"results": [
        {"id": 1, "name": "Show A", "original_name": "Show A",
         "first_air_date": "2010-01-01", "popularity": 10},
        {"id": 2, "name": "Show B", "original_name": "Show B",
         "first_air_date": "2011-01-01", "popularity": 20}]}
    ctrl = _controller(c, tmp_cache_dir)
    p = parse_filename("Ambiguous.S01E01.mkv")
    batch = ctrl.create_batch("ambiguous",
                              [(Path("Ambiguous.S01E01.mkv"), p)], "en-US")
    seen = _drive(ctrl, batch, {Action.NEED_SELECTION})
    assert Action.NEED_SELECTION in seen
