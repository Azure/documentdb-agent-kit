"""Regression guards for the committed ecommerce-advanced dataset."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import kit


pytestmark = pytest.mark.advanceddata

SCENARIO = kit.REPO_DIR / "scenarios" / "ecommerce-advanced"
DATA = SCENARIO / "data"


def read_json(path):
    return json.loads(path.read_text())


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_committed_files_match_manifest():
    manifest = read_json(DATA / "manifest.json")

    assert manifest["seed"] == 20260901
    assert manifest["generated_at"] == "2026-09-01T00:00:00.000Z"
    assert manifest["data_epoch"] == "2025-01-01T00:00:00.000Z"
    assert manifest["collection_counts"] == {
        "customers": 200,
        "products": 100,
        "inventory": 300,
        "orders": 2000,
        "order_items": 6000,
        "payments": 2000,
        "returns": 120,
        "daily_sales": 84,
        "stream_orders": 2,
    }

    for spec in manifest["files"]:
        content = (DATA / spec["path"]).read_bytes()
        assert len(content) == spec["bytes"], spec["path"]
        assert hashlib.sha256(content).hexdigest() == spec["sha256"], spec["path"]


def test_transaction_and_time_series_edge_cases_are_present():
    cases = read_json(DATA / "cases" / "transactions.json")
    by_id = {case["case_id"]: case for case in cases}

    assert by_id["commit-purchase"]["initial_quantity"] == 10
    assert by_id["commit-purchase"]["expected_quantity"] == 8
    assert by_id["concurrent-last-unit"]["initial_quantity"] == 1
    assert by_id["concurrent-last-unit"]["expected_commits"] == 1
    assert by_id["insufficient-stock"]["initial_quantity"] == 0
    assert by_id["forced-rollback"]["failure_after"] == "payment_insert"

    daily_sales = read_jsonl(DATA / "collections" / "daily_sales.jsonl")
    assert len(daily_sales) == 84
    assert sum(row["revenue"] is None for row in daily_sales) == 3


def test_generator_reproduces_byte_identical_output():
    if not shutil.which("node"):
        pytest.skip("Node.js is required to run the deterministic generator")

    result = subprocess.run(
        ["bash", "scripts/check-determinism.sh"],
        cwd=SCENARIO,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "byte-identical" in result.stdout
