"""Scenario conftest: benchmark config validation needs no database."""

import pytest


@pytest.fixture(scope="session", autouse=True)
def require_container():
    """No-op override — this scenario only reads files."""
    return None
