"""Scenario conftest: token accounting needs NO database.

The root conftest has an autouse fixture that skips (or aborts) when the
DocumentDB container is unavailable. This scenario tests pure arithmetic over a
synthetic SQLite file, so it overrides that fixture with a no-op. Defining a
fixture of the same name in a nested conftest shadows the parent's.

The practical benefit: these tests run in CI on every PR with no Docker, no
container and no credentials.
"""

import sys
from pathlib import Path

import pytest

# The module under test lives in the Cross-Model Skill Evaluations folder (it measures agent cost), but
# it is plain stdlib Python, so Diagnostic Regression Suite can and should regression-test it.
HARNESS = Path(__file__).resolve().parents[3] / "evals" / "harness"
sys.path.insert(0, str(HARNESS))


@pytest.fixture(scope="session", autouse=True)
def require_container():
    """No-op override — this scenario is infrastructure-free."""
    return None
