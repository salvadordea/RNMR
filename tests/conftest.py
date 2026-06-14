"""Shared pytest configuration and fixtures for the RNMR test suite."""
import os
import sys
import tempfile
from pathlib import Path

# Qt must run headless in CI / automated runs.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# A dummy key keeps the GUI from probing for one; tests never hit the network.
os.environ.setdefault("TMDB_API_KEY", "dummy_test_key")

# Ensure the project root is importable regardless of the invocation dir.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from renamer.cache import Cache
from renamer.tmdb import TMDBClient


@pytest.fixture
def tmp_cache_dir():
    """A throwaway directory for an isolated cache file."""
    return Path(tempfile.mkdtemp())


@pytest.fixture
def client(tmp_cache_dir):
    """A TMDBClient with an isolated cache and no real network.

    Tests assign ``client._request = <fake>`` to control responses.
    """
    return TMDBClient(api_key="x", cache=Cache(tmp_cache_dir))
