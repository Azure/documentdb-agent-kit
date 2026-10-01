"""This scenario validates committed files and needs no database container."""

import pytest


@pytest.fixture(scope="session", autouse=True)
def require_container():
    return None

