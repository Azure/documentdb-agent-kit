"""Scenario conftest: route-efficiency config validation needs no database."""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "benchmarks" / "documentdb-route-efficiency" / "shared" / "verifier"))


@pytest.fixture(scope="session", autouse=True)
def require_container():
    """No-op override — this scenario only reads files and grades JSON."""
    return None
