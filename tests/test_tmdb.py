"""Tests for the TMDB client (network mocked via client._request)."""
from renamer.cache import Cache
from renamer.tmdb import TMDBClient, similarity_score


def _season_payload(n):
    return {"episodes": [{"episode_number": i, "name": f"Ep {i}"}
                         for i in range(1, n + 1)]}


def test_get_season_details_single_request(client):
    calls = []

    def fake(endpoint, params=None, retries=3):
        calls.append(endpoint)
        return _season_payload(24)

    client._request = fake
    eps = client.get_season_details(100, 1)
    assert len(eps) == 24
    assert len(calls) == 1  # one request for the whole season
    assert eps[12].name == "Ep 12"


def test_season_fetch_populates_episode_cache(tmp_cache_dir):
    c = TMDBClient(api_key="x", cache=Cache(tmp_cache_dir))
    c._request = lambda e, params=None, retries=3: {
        "episodes": [{"episode_number": 1, "name": "Pilot"}]}
    c.get_season_details(100, 1)

    # A second client reads the persisted cache without any network.
    c2 = TMDBClient(api_key="x", cache=Cache(tmp_cache_dir))

    def boom(*a, **k):
        raise AssertionError("should not hit the network")

    c2._request = boom
    assert c2.get_episode_details(100, 1, 1).name == "Pilot"


def test_movie_search_prefers_exact_and_year(client):
    client._request = lambda e, params=None, retries=3: {"results": [
        {"id": 1, "title": "The Matrix", "original_title": "The Matrix",
         "release_date": "1999-03-31", "popularity": 80},
        {"id": 2, "title": "Matrix Reloaded", "original_title": "Matrix Reloaded",
         "release_date": "2003-05-15", "popularity": 50},
    ]}
    m = client.search_movie("The Matrix", 1999)
    assert m is not None
    assert m.id == 1


def test_similarity_scoring_is_sane():
    assert similarity_score("The Matrix", "the matrix") > 0.95
    assert similarity_score("Dark", "Breaking Bad") < 0.5
