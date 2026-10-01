"""Importable helpers for scenario conftests.

This module is on sys.path (added by the root conftest) but is itself NOT a
pytest conftest, so it must not define pytest hooks. Global fixtures and the
pytest_addoption hook live in the root testing/conftest.py instead.
"""

import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HARNESS_DIR))

import pytest  # noqa: E402

import kit  # noqa: E402,F401  (re-used by scenario tests via `import kit`)


def make_seeded_db_fixture(db_name, scenario_dir, fixture_filename="fixture.js"):
    """Build a session-scoped `seeded_db` fixture for one scenario.

    Usage in a scenario's conftest.py:
        from conftest_base import make_seeded_db_fixture
        seeded_db = make_seeded_db_fixture("test_xyz", Path(__file__).resolve().parent)
    """
    fixture = Path(scenario_dir) / fixture_filename

    @pytest.fixture(scope="session")
    def seeded_db(request, require_container):
        container_name = require_container
        if not fixture.exists():
            raise FileNotFoundError(f"fixture not found: {fixture}")
        kit.drop_db(db_name, container=container_name)
        kit.seed(db_name, fixture, container=container_name)
        yield db_name
        if not request.config.getoption("--keep-db"):
            kit.drop_db(db_name, container=container_name)

    return seeded_db
