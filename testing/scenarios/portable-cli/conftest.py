"""Portable CLI tests need no live database."""

import pytest


@pytest.fixture(scope="session", autouse=True)
def require_container():
    return None
