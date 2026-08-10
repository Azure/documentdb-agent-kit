"""Root conftest: defines the CLI options and global fixtures shared by every
scenario. Scenario conftests only build their own `seeded_db` fixture via
`make_seeded_db_fixture`.
"""

import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent / "harness"
sys.path.insert(0, str(HARNESS_DIR))

import yaml  # noqa: E402
import pytest  # noqa: E402

import kit  # noqa: E402


def pytest_addoption(parser):
    parser.addoption("--container", action="store", default=None,
                     help="DocumentDB container name (default: env DOCDB_CONTAINER "
                          "or documentdb-local)")
    parser.addoption("--keep-db", action="store_true", default=False,
                     help="Do not drop the scenario database after the run")


@pytest.fixture(scope="session")
def container_name(request):
    return request.config.getoption("--container") or kit.CONTAINER


@pytest.fixture(scope="session", autouse=True)
def require_container(container_name):
    """Skip everything if the DocumentDB container isn't running or no password
    is configured (credentials are never baked in — set DOCDB_PASSWORD or
    DB_PASSWORD)."""
    if not kit.DB_PASSWORD:
        pytest.skip("No DB password configured — set DOCDB_PASSWORD or DB_PASSWORD "
                    "(e.g. export DB_PASSWORD='<your-password>')")
    if not kit.container_running(container_name):
        pytest.skip(f"DocumentDB container '{container_name}' is not running "
                    f"(start it, or pass --container / set DOCDB_CONTAINER)")


@pytest.fixture
def expected(request):
    """Load the nearest expected-findings.yaml walking up from the test file."""
    p = Path(request.path).resolve()
    for parent in [p.parent, *p.parents]:
        candidate = parent / "expected-findings.yaml"
        if candidate.exists():
            with open(candidate) as fh:
                return yaml.safe_load(fh)
    raise FileNotFoundError("expected-findings.yaml not found for this scenario")
