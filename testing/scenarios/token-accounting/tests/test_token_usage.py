"""Contract tests for evals/harness/token_usage.py (Cross-Model Skill Evaluations cost accounting).

These tests exist because the cost numbers are the ones that will end up in a
GTM claim, and a quietly wrong denominator is the easiest way to publish a false
result. Each test pins one thing that could silently mislead:

* cache_read is a SUBSET of input, so "fresh input" must subtract it
* a run that never went green must NOT report a cost-to-green
* credits-per-pass must be undefined (not 0, not infinity) when nothing passed
* a single run must not be presented as a comparable mean

Everything runs against a synthetic SQLite file — no container, no credentials,
no network.
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

import token_usage as tu

pytestmark = pytest.mark.tokens


# ---------------------------------------------------------------------------
# synthetic session store
# ---------------------------------------------------------------------------
def _make_store(tmp_path: Path, rows, sessions=("s1",)) -> Path:
    """Build a minimal session-store.db with the two tables we read."""
    db = tmp_path / "session-store.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE sessions (
        id TEXT, cwd TEXT, repository TEXT, host_type TEXT, branch TEXT,
        summary TEXT, created_at TEXT, updated_at TEXT)""")
    conn.execute("""CREATE TABLE assistant_usage_events (
        id INTEGER PRIMARY KEY, session_id TEXT, turn_index INTEGER,
        agent_id TEXT, parent_tool_call_id TEXT, model TEXT,
        input_tokens INTEGER, output_tokens INTEGER, cache_read_tokens INTEGER,
        cache_write_tokens INTEGER, reasoning_tokens INTEGER,
        total_nano_aiu INTEGER, request_multiplier REAL, duration_ms INTEGER,
        time_to_first_token_ms INTEGER, inter_token_latency_ms INTEGER,
        initiator TEXT, api_endpoint TEXT, reasoning_effort TEXT,
        finish_reason TEXT, content_filter_triggered INTEGER,
        token_details_json TEXT, created_at TEXT)""")
    for sid in sessions:
        conn.execute("INSERT INTO sessions (id, created_at) VALUES (?, ?)",
                     (sid, "2026-08-12T00:00:00Z"))
    conn.executemany(
        """INSERT INTO assistant_usage_events
           (session_id, turn_index, agent_id, model, input_tokens,
            output_tokens, cache_read_tokens, cache_write_tokens,
            reasoning_tokens, total_nano_aiu, duration_ms)
           VALUES (:session_id, :turn_index, :agent_id, :model, :input_tokens,
                   :output_tokens, :cache_read_tokens, :cache_write_tokens,
                   :reasoning_tokens, :total_nano_aiu, :duration_ms)""",
        rows,
    )
    conn.commit()
    conn.close()
    return db


def _row(**kw):
    base = dict(session_id="s1", turn_index=0, agent_id=None, model="m1",
                input_tokens=1000, output_tokens=100, cache_read_tokens=0,
                cache_write_tokens=0, reasoning_tokens=0,
                total_nano_aiu=1_000_000_000, duration_ms=1000)
    base.update(kw)
    return base


@pytest.fixture
def store(tmp_path):
    rows = [
        _row(turn_index=0, input_tokens=1000, cache_read_tokens=0,
             output_tokens=100, total_nano_aiu=2_000_000_000, duration_ms=1500),
        _row(turn_index=1, input_tokens=5000, cache_read_tokens=4500,
             output_tokens=200, total_nano_aiu=3_000_000_000, duration_ms=2500),
        _row(turn_index=1, input_tokens=5000, cache_read_tokens=4800,
             output_tokens=50, total_nano_aiu=1_000_000_000, duration_ms=500,
             agent_id="explore"),
    ]
    return _make_store(tmp_path, rows)


# ---------------------------------------------------------------------------
# rollup arithmetic
# ---------------------------------------------------------------------------
def test_rollup_sums_every_request(store):
    conn, tmp = tu._open_readonly(store)
    try:
        u = tu.session_usage(conn, "s1")
    finally:
        tu._cleanup(conn, tmp)

    assert u["requests"] == 3
    # turn_index 1 appears twice (main + subagent) but is ONE turn
    assert u["turns"] == 2
    assert u["input_tokens"] == 11000
    assert u["output_tokens"] == 350


def test_fresh_input_subtracts_cache_reads(store):
    """The headline honesty check.

    cache_read_tokens is a subset of input_tokens (verified against the real
    store: 0 of 6,348 rows had cache_read > input). Reporting raw input as the
    cost of a skill would overstate it by an order of magnitude.
    """
    conn, tmp = tu._open_readonly(store)
    try:
        u = tu.session_usage(conn, "s1")
    finally:
        tu._cleanup(conn, tmp)

    assert u["cache_read_tokens"] == 9300
    assert u["fresh_input_tokens"] == 11000 - 9300
    assert u["cache_read_share"] == pytest.approx(9300 / 11000, abs=1e-4)


def test_credits_convert_from_nano_aiu(store):
    conn, tmp = tu._open_readonly(store)
    try:
        u = tu.session_usage(conn, "s1")
    finally:
        tu._cleanup(conn, tmp)
    assert u["credits"] == pytest.approx(6.0)


def test_subagent_spend_is_reported_separately(store):
    """Subagent cost is real cost. Reporting only the main agent would
    understate any skill that delegates."""
    conn, tmp = tu._open_readonly(store)
    try:
        agents = {a["agent"]: a for a in tu.by_agent(conn, "s1")}
    finally:
        tu._cleanup(conn, tmp)

    assert set(agents) == {"main", "explore"}
    assert agents["explore"]["credits"] == pytest.approx(1.0)
    assert agents["main"]["credits"] == pytest.approx(5.0)


def test_fresh_input_never_negative(tmp_path):
    """Defensive: if the provider ever reports cache_read > input, the metric
    must clamp rather than produce a negative 'cost'."""
    db = _make_store(tmp_path, [_row(input_tokens=100, cache_read_tokens=500)])
    conn, tmp = tu._open_readonly(db)
    try:
        u = tu.session_usage(conn, "s1")
    finally:
        tu._cleanup(conn, tmp)
    assert u["fresh_input_tokens"] == 0


# ---------------------------------------------------------------------------
# outcome handling
# ---------------------------------------------------------------------------
def test_failed_run_reports_no_cost_to_green(store):
    """A run that gave up early is cheap. If we let it report a cost-to-green,
    failure would look like efficiency."""
    conn, tmp = tu._open_readonly(store)
    try:
        rep = tu.build_report(conn, "s1", {"model": "m1", "arm": "skills"},
                              {"tests_passed": 3, "tests_total": 10,
                               "green": False})
    finally:
        tu._cleanup(conn, tmp)

    assert rep["cost_to_green"]["green"] is False
    assert rep["cost_to_green"]["credits_to_green"] is None
    assert rep["cost_to_green"]["turns_to_green"] is None


def test_green_run_reports_cost_to_green(store):
    conn, tmp = tu._open_readonly(store)
    try:
        rep = tu.build_report(conn, "s1", {"model": "m1", "arm": "skills"},
                              {"tests_passed": 10, "tests_total": 10,
                               "green": True})
    finally:
        tu._cleanup(conn, tmp)

    assert rep["cost_to_green"]["credits_to_green"] == pytest.approx(6.0)
    assert rep["cost_to_green"]["turns_to_green"] == 2
    # tokens_to_green uses FRESH input, not raw input
    assert rep["cost_to_green"]["tokens_to_green"] == 1700 + 350


def test_missing_session_fails_loudly(store):
    conn, tmp = tu._open_readonly(store)
    try:
        with pytest.raises(SystemExit):
            tu.build_report(conn, "does-not-exist", {}, None)
    finally:
        tu._cleanup(conn, tmp)


# ---------------------------------------------------------------------------
# comparison
# ---------------------------------------------------------------------------
def _report(model, arm, credits, turns, green, fresh=1000):
    return {
        "task": {"model": model, "arm": arm},
        "usage": {"credits": credits, "turns": turns,
                  "fresh_input_tokens": fresh, "cache_read_share": 0.9},
        "outcome": {"green": green},
    }


def test_compare_groups_by_model_and_arm():
    reports = [
        _report("m1", "skills", 10, 5, True),
        _report("m1", "skills", 12, 6, True),
        _report("m1", "control", 8, 9, False),
    ]
    cells = {(c["model"], c["arm"]): c for c in tu.compare(reports)["cells"]}
    assert set(cells) == {("m1", "skills"), ("m1", "control")}
    assert cells[("m1", "skills")]["runs"] == 2
    assert cells[("m1", "skills")]["pass_rate"] == 1.0
    assert cells[("m1", "control")]["pass_rate"] == 0.0


def test_credits_per_pass_is_none_when_nothing_passed():
    """Must not be 0 (looks free) or a divide-by-zero crash."""
    cells = tu.compare([_report("m1", "control", 8, 9, False)])["cells"]
    assert cells[0]["credits_per_pass"] is None


def test_credits_per_pass_charges_failures_to_the_successes():
    """Three runs costing 10 credits each, one of which passed, means a passing
    result cost 30 — not 10. Failed attempts are part of the price."""
    reports = [
        _report("m1", "skills", 10, 5, True),
        _report("m1", "skills", 10, 5, False),
        _report("m1", "skills", 10, 5, False),
    ]
    cells = tu.compare(reports)["cells"]
    assert cells[0]["credits_per_pass"] == pytest.approx(30.0)


def test_underpowered_cells_are_flagged():
    """Agent runs are non-deterministic; a mean over one run is not a result."""
    cells = tu.compare([_report("m1", "skills", 10, 5, True)])["cells"]
    assert cells[0]["underpowered"] is True
    assert cells[0]["runs"] == 1

    reports = [_report("m1", "skills", 10, 5, True) for _ in range(3)]
    assert tu.compare(reports)["cells"][0]["underpowered"] is False


def test_render_table_marks_underpowered_and_undefined():
    table = tu.render_table(tu.compare([_report("m1", "control", 8, 9, False)]))
    assert "⚠️" in table
    assert "| — |" in table  # credits/pass undefined, not 0


def test_standard_deviation_is_reported():
    """A mean without a spread invites over-claiming a difference that is noise."""
    reports = [
        _report("m1", "skills", 10, 5, True),
        _report("m1", "skills", 20, 5, True),
    ]
    cell = tu.compare(reports)["cells"][0]
    assert cell["credits"]["mean"] == pytest.approx(15.0)
    assert cell["credits"]["sd"] > 0


# ---------------------------------------------------------------------------
# snapshot safety
# ---------------------------------------------------------------------------
def test_reader_does_not_lock_or_mutate_the_source(store):
    """The CLI may be writing to the store while we read it. We must snapshot,
    never open the live file for writing."""
    before = store.read_bytes()
    conn, tmp = tu._open_readonly(store)
    try:
        tu.session_usage(conn, "s1")
    finally:
        tu._cleanup(conn, tmp)
    assert store.read_bytes() == before
    assert not tmp.exists(), "temp snapshot must be cleaned up"


def test_missing_store_gives_an_actionable_error(tmp_path):
    with pytest.raises(SystemExit) as e:
        tu._open_readonly(tmp_path / "nope.db")
    assert "Copilot CLI" in str(e.value)
