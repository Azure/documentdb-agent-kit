"""Shared pytest fixtures for the documentdb-sdk-skills verifier.

The verifier is **contract-driven**, mirroring the Cosmos benchmark's design.
Each task image bakes a scenario contract (shared/contracts/<scenario>.json,
copied to /verifier/contracts/) and selects it with the SCENARIO env var. The
contract declares, per scenario:

  * the DocumentDB database + collection env vars and their defaults,
  * the "root" entities reachable via create/get/list, their deterministic seed
    data, field shapes, modelling / indexing expectations, and
  * the engine-level expectations (scan amplification, forbidden full scans).

Everything is read from environment variables the base image and the per-task
test.sh set up:

    SCENARIO                       -- orders (selects the contract)
    SDK                            -- python | dotnet | java | nodejs | go
    APP_PORT                       -- port the agent's app should listen on
    APP_WORKDIR                    -- where the agent put its source (/app)
    DOCUMENTDB_HOST/PORT/USER      -- Mongo-API connection
    DOCUMENTDB_PASSWORD            -- generated per container, never baked in
    DOCUMENTDB_DATABASE            -- scenario database
    DOCUMENTDB_*_COLLECTION        -- per-entity collection names
    PG_PORT / PG_USER / PG_DB      -- the PostgreSQL engine underneath
    VERIFIER_LOG_DIR               -- where per-check logs land

The verifier owns no test data: seed data lives in the contract and is inserted
through the agent's own API, so an app that answers HTTP without persisting
fails the behavioural gate.

TWO OBSERVATION PLANES
----------------------
Unlike the Cosmos equivalent, this verifier can observe the system two ways:
the Mongo API (`pymongo`) and the PostgreSQL engine underneath (`psycopg`).
Client-side properties Cosmos can only regex out of source code — index usage,
connection reuse — are checked BEHAVIOURALLY here. See check_engine.py.
"""
from __future__ import annotations

import json
import re
import os
import time
from pathlib import Path

import pytest
import requests

SDK_ALIASES = {
    "py": "python", "python": "python",
    "dotnet": "dotnet", ".net": "dotnet", "csharp": "dotnet",
    "java": "java",
    "node": "nodejs", "nodejs": "nodejs", "javascript": "nodejs", "js": "nodejs",
    "go": "go", "golang": "go",
}

CONTRACTS_DIR = Path(os.environ.get("CONTRACTS_DIR", "/verifier/contracts"))


# ---------------------------------------------------------------------
# Contract loading (module level so check_*.py can parametrize on it)
# ---------------------------------------------------------------------
def load_contract() -> dict:
    """Load the scenario contract selected by SCENARIO.

    Fails loudly rather than silently grading nothing: a mis-wired task image
    that grades an empty contract would report success for any submission,
    which is far worse than an error.
    """
    scenario = os.environ.get("SCENARIO", "orders")
    path = CONTRACTS_DIR / f"{scenario}.json"
    if not path.is_file():
        available = (
            sorted(p.name for p in CONTRACTS_DIR.glob("*.json"))
            if CONTRACTS_DIR.is_dir() else "contracts dir missing"
        )
        raise RuntimeError(
            f"Scenario contract not found: {path}. SCENARIO={scenario!r}. "
            f"Available: {available}"
        )
    return json.loads(path.read_text())


CONTRACT = load_contract()
ROOTS = CONTRACT.get("roots", [])


def root_ids(root: dict) -> str:
    return root["name"]


def fmt_path(template: str, **kw) -> str:
    return template.format(**kw)


def collection_name(root: dict) -> str:
    return os.environ.get(
        root.get("collection_env", ""), root.get("collection_default", root["name"])
    )


def database_name() -> str:
    return os.environ.get(
        CONTRACT.get("database_env", "DOCUMENTDB_DATABASE"),
        CONTRACT.get("database_default", "ordersdb"),
    )


# ---------------------------------------------------------------------
# environment
# ---------------------------------------------------------------------
@pytest.fixture(scope="session")
def sdk() -> str:
    raw = os.environ.get("SDK", "python").strip().lower()
    return SDK_ALIASES.get(raw, raw)


@pytest.fixture(scope="session")
def app_port() -> int:
    return int(os.environ.get("APP_PORT", "9080"))


@pytest.fixture(scope="session")
def app_dir() -> Path:
    return Path(os.environ.get("APP_WORKDIR", "/app"))


@pytest.fixture(scope="session")
def base_url(app_port) -> str:
    return f"http://localhost:{app_port}"


# ---------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------
class Api:
    """Thin HTTP helper with a short timeout.

    A hung request must fail the check rather than stall the whole verifier
    until Harbor's task timeout kills it with no diagnosis.
    """

    def __init__(self, base_url: str, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path if path.startswith('/') else '/' + path}"

    def get(self, path, **kw):
        return self.session.get(self._url(path), timeout=self.timeout, **kw)

    def post(self, path, **kw):
        return self.session.post(self._url(path), timeout=self.timeout, **kw)


@pytest.fixture(scope="session")
def api(base_url) -> Api:
    return Api(base_url)


# ---------------------------------------------------------------------
# database clients — the verifier's OWN, independent of the agent's
# ---------------------------------------------------------------------
@pytest.fixture(scope="session")
def mongo_uri() -> str:
    host = os.environ.get("DOCUMENTDB_HOST", "localhost")
    port = os.environ.get("DOCUMENTDB_PORT", "10260")
    user = os.environ.get("DOCUMENTDB_USER", "docdbadmin")
    pwd = os.environ.get("DOCUMENTDB_PASSWORD", "")
    if not pwd:
        pytest.fail(
            "DOCUMENTDB_PASSWORD is not set in the verifier environment. "
            "start-documentdb generates it and runner.sh must export it."
        )
    from urllib.parse import quote_plus
    return (
        f"mongodb://{quote_plus(user)}:{quote_plus(pwd)}@{host}:{port}/"
        "?authMechanism=SCRAM-SHA-256&tls=true&tlsAllowInvalidCertificates=true"
        "&directConnection=true"
    )


@pytest.fixture(scope="session")
def mongo(mongo_uri):
    """The verifier's own pymongo client.

    Deliberately independent of the agent's client: every persistence claim is
    checked by reading the database ourselves, so an app that answers HTTP from
    an in-memory dict cannot pass.
    """
    from pymongo import MongoClient
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=20000)
    client.admin.command("ping")
    yield client
    client.close()


@pytest.fixture(scope="session")
def db(mongo):
    return mongo[database_name()]


@pytest.fixture(scope="session")
def pg():
    """Connection to the PostgreSQL engine underneath DocumentDB.

    This is the second observation plane, and the thing that makes this
    benchmark stronger than a Mongo-API-only grader: index usage and scan
    behaviour can be proven from the engine's own statistics rather than
    inferred from source code.
    """
    psycopg = pytest.importorskip("psycopg", reason="psycopg not installed")
    conn = psycopg.connect(
        host=os.environ.get("DOCUMENTDB_HOST", "localhost"),
        port=int(os.environ.get("PG_PORT", "9712")),
        user=os.environ.get("PG_USER", "documentdb"),
        dbname=os.environ.get("PG_DB", "postgres"),
        connect_timeout=20,
    )
    conn.autocommit = True
    yield conn
    conn.close()


# ---------------------------------------------------------------------
# seeding through the agent's API
# ---------------------------------------------------------------------
@pytest.fixture(scope="session")
def seed_roots(api):
    """POST the contract's seed rows through the agent's own API.

    Seeding through the API (rather than writing to the database directly) is
    what makes the later reads meaningful: it tests the agent's write path.
    """
    created = {}
    for root in ROOTS:
        create = root.get("create")
        if not create:
            continue
        rows = []
        for row in root["seed"]:
            resp = api.post(create["path"], json=row)
            rows.append({"row": row, "status": resp.status_code,
                         "body": _safe_json(resp)})
        created[root["name"]] = rows
    # Give the engine a moment to make writes visible to an independent reader.
    time.sleep(1.0)
    return created


def _safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return None


@pytest.fixture(scope="session")
def root_persisted(db, seed_roots):
    """Read every seeded id back with the VERIFIER's own client."""
    out = {}
    for root in ROOTS:
        coll = db[collection_name(root)]
        docs = {}
        for row in root["seed"]:
            docs[row["id"]] = _find_by_logical_id(coll, row["id"])
        out[root["name"]] = docs
    return out


def _find_by_logical_id(coll, logical_id):
    """Find a document by the id the API was given.

    The agent may store it as `_id` or as a separate `id` field; both are
    legitimate modelling choices, so accept either rather than dictating one.
    """
    doc = coll.find_one({"_id": logical_id})
    if doc is None:
        doc = coll.find_one({"id": logical_id})
    return doc


def emulator_docs_for_id(db, root, logical_id):
    return _find_by_logical_id(db[collection_name(root)], logical_id)


# ---------------------------------------------------------------------
# realistic volume, for the engine checks only
# ---------------------------------------------------------------------
FILLER_COUNT = int(os.environ.get("VERIFIER_FILLER_DOCS", "20000"))


@pytest.fixture(scope="session")
def bulk_filler(db, seed_roots):
    """Bulk-load filler documents so the engine checks are meaningful.

    WHY THIS IS NECESSARY, not a workaround: on a 4-document collection a
    sequential scan is genuinely the cheaper plan, and PostgreSQL is right to
    choose it. Grading index usage at that size would test nothing — the oracle
    itself would fail. The task tells the agent the service runs against
    "millions of orders", so the verifier must grade at a size where that
    statement has consequences.

    Written by the VERIFIER directly, not through the API: this is background
    volume, not a test of the agent's write path. Filler uses a disjoint
    customer_id namespace (FILLER-*) so it cannot affect the filtered-list
    assertions in check_api.
    """
    from pymongo import InsertOne

    inserted = {}
    for root in ROOTS:
        coll = db[collection_name(root)]
        existing = coll.count_documents({"customer_id": {"$regex": "^FILLER-"}})
        if existing >= FILLER_COUNT:
            inserted[root["name"]] = existing
            continue

        ops, batch = [], 0
        for i in range(FILLER_COUNT - existing):
            ops.append(InsertOne({
                "_id": f"filler-{i}",
                "customer_id": f"FILLER-{i % 4000}",
                "status": ["shipped", "pending", "cancelled"][i % 3],
                "amount": float((i % 500) + 10),
                "items": ["filler"],
            }))
            if len(ops) >= 2000:
                coll.bulk_write(ops, ordered=False)
                batch += len(ops)
                ops = []
        if ops:
            coll.bulk_write(ops, ordered=False)
            batch += len(ops)
        inserted[root["name"]] = batch

    # ANALYZE so the planner costs against real statistics rather than the
    # defaults it assumed when the table was tiny.
    try:
        import psycopg
        with psycopg.connect(
            host=os.environ.get("DOCUMENTDB_HOST", "localhost"),
            port=int(os.environ.get("PG_PORT", "9712")),
            user=os.environ.get("PG_USER", "documentdb"),
            dbname=os.environ.get("PG_DB", "postgres"),
            connect_timeout=20,
        ) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("ANALYZE")
    except Exception:
        # Statistics are an optimisation, not a correctness requirement.
        pass

    return inserted


# ---------------------------------------------------------------------
# source scanning (for the WEAKER, static half of the grader)
#
# ANTI-GAMING: comments are stripped before any regex runs, so an agent
# cannot satisfy a check by writing "# uses a singleton MongoClient" in a
# comment. String literals are deliberately NOT stripped, so patterns in
# check_source.py must require code adjacency (`foo\s*=`, `Foo\s*\(`)
# rather than a bare keyword a log message could satisfy by accident.
# ---------------------------------------------------------------------
SOURCE_SUFFIXES = {
    "python": {".py"},
    "dotnet": {".cs", ".csproj"},
    "java": {".java", ".xml", ".gradle"},
    "nodejs": {".js", ".ts", ".mjs", ".cjs", ".json"},
    "go": {".go", ".mod"},
}
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "bin", "obj", "target", "dist", "build", ".pytest_cache", "site-packages",
}

_TRIPLE_DOUBLE = re.compile(r'"""(?:.|\n)*?"""')
_TRIPLE_SINGLE = re.compile(r"'''(?:.|\n)*?'''")
_HASH_LINE = re.compile(r"#[^\n]*")
_BLOCK_C = re.compile(r"/\*(?:.|\n)*?\*/")
_SLASH_LINE = re.compile(r"//[^\n]*")
_XML_COMMENT = re.compile(r"<!--(?:.|\n)*?-->")


def _strip_comments(text: str, sdk: str) -> str:
    if sdk == "python":
        text = _TRIPLE_DOUBLE.sub("", text)
        text = _TRIPLE_SINGLE.sub("", text)
        return _HASH_LINE.sub("", text)
    if sdk == "go":
        text = _BLOCK_C.sub("", text)
        return _SLASH_LINE.sub("", text)
    text = _XML_COMMENT.sub("", text)
    text = _BLOCK_C.sub("", text)
    return _SLASH_LINE.sub("", text)


@pytest.fixture(scope="session")
def workdir(app_dir) -> Path:
    return app_dir


@pytest.fixture(scope="session")
def source_files(sdk, workdir) -> list:
    suffixes = SOURCE_SUFFIXES.get(sdk, {".py"})
    out = []
    if not workdir.exists():
        return out
    for p in workdir.rglob("*"):
        if not p.is_file() or any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix in suffixes:
            out.append(p)
    return out


@pytest.fixture(scope="session")
def source_text(sdk, source_files) -> str:
    """All source concatenated, comments stripped."""
    chunks = []
    for p in source_files:
        try:
            chunks.append(_strip_comments(p.read_text(encoding="utf-8", errors="ignore"), sdk))
        except OSError:
            pass
    return "\n".join(chunks)


@pytest.fixture(scope="session")
def source_text_raw(source_files) -> str:
    """Source WITHOUT comment stripping.

    Used only where a comment genuinely counts as a finding — a hardcoded
    credential is a leak whether or not it sits in a comment.
    """
    chunks = []
    for p in source_files:
        try:
            chunks.append(p.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            pass
    return "\n".join(chunks)
