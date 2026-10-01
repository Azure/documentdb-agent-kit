"""Contract tests for the MSBench cost-metric harvester (MSBench Skill-Efficacy Benchmark).

WHY THIS SCENARIO EXISTS
------------------------
MSBench's reward is binary: complied, or did not. That cannot answer "what did
it cost?" or "which kind of task is expensive?", which is half of what we want
from the benchmark. `harvest_metrics.py` fills that gap by writing MSBench's
per-instance `custom_metrics.json`.

Two failure modes make those numbers dangerous rather than merely absent, and
both are pinned here:

1. **Silent divergence from the Cross-Model Skill Evaluation cost module.**
   We now have two places that compute "what did the agent cost" —
   `evals/harness/token_usage.py` (Cross-Model Skill Evaluations) and
   `benchmarks/.../harvest_metrics.py` (MSBench Skill-Efficacy Benchmark).
   They must agree, or we will publish two different cost figures for the same
   run. They cannot share an import (the harvester has to run inside a minimal
   task container), so consistency is pinned by TEST instead of by import path.

2. **A zero that means "not measured".** If harvesting fails, a missing metric
   is honest; a silent 0 corrupts every average computed over it.

Infrastructure-free: synthetic SQLite, no container, no credentials, no
network. Runs on every PR.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import harvest_metrics as hm
import token_usage as tu

pytestmark = pytest.mark.benchmarkmetrics


# ---------------------------------------------------------------------------
# synthetic session store (shared shape with the token-accounting scenario)
# ---------------------------------------------------------------------------
def _make_store(tmp_path: Path, rows) -> Path:
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
    conn.execute("INSERT INTO sessions (id, created_at) VALUES ('s1','2026-08-13T00:00:00Z')")
    conn.executemany(
        """INSERT INTO assistant_usage_events
           (session_id, turn_index, agent_id, model, input_tokens, output_tokens,
            cache_read_tokens, cache_write_tokens, reasoning_tokens,
            total_nano_aiu, duration_ms)
           VALUES (:session_id,:turn_index,:agent_id,:model,:input_tokens,
                   :output_tokens,:cache_read_tokens,:cache_write_tokens,
                   :reasoning_tokens,:total_nano_aiu,:duration_ms)""",
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
    return _make_store(tmp_path, [
        _row(turn_index=0, input_tokens=1000, cache_read_tokens=0,
             output_tokens=100, total_nano_aiu=2_000_000_000, duration_ms=1500),
        _row(turn_index=1, input_tokens=5000, cache_read_tokens=4500,
             output_tokens=200, total_nano_aiu=3_000_000_000, duration_ms=2500),
        _row(turn_index=1, input_tokens=5000, cache_read_tokens=4800,
             output_tokens=50, total_nano_aiu=1_000_000_000, duration_ms=500,
             agent_id="explore"),
    ])


def _ctrf(tmp_path, tests) -> Path:
    p = tmp_path / "ctrf.json"
    p.write_text(json.dumps({"results": {"tests": tests}}))
    return p


def _reward(tmp_path, value) -> Path:
    p = tmp_path / "reward.txt"
    p.write_text(str(value))
    return p


# ---------------------------------------------------------------------------
# THE consistency guarantee
# ---------------------------------------------------------------------------
def test_harvester_agrees_with_the_skill_evaluation_cost_module(store):
    """The two cost implementations must produce identical numbers.

    They deliberately do not share code — the harvester must be self-contained
    to run inside a minimal task container — so this test is what stops them
    drifting into two different published cost figures for the same run.
    """
    harvested = hm.read_usage(store)

    conn, tmp = tu._open_readonly(store)
    try:
        skill_evaluation = tu._derive(dict(conn.execute(
            tu._ROLLUP_SQL.replace("WHERE session_id = ?", "")
        ).fetchone()))
    finally:
        tu._cleanup(conn, tmp)

    for hkey, tkey in [
        ("tokens_input", "input_tokens"),
        ("tokens_output", "output_tokens"),
        ("tokens_cache_read", "cache_read_tokens"),
        ("tokens_fresh_input", "fresh_input_tokens"),
        ("tokens_reasoning", "reasoning_tokens"),
        ("ai_credits", "credits"),
        ("agent_turns", "turns"),
        ("agent_requests", "requests"),
    ]:
        assert harvested[hkey] == pytest.approx(skill_evaluation[tkey]), (
            f"cost definitions have drifted: harvest_metrics.{hkey}="
            f"{harvested[hkey]} but token_usage.{tkey}={skill_evaluation[tkey]}"
        )


def test_fresh_input_subtracts_cache_reads(store):
    """The honesty metric: cache_read is a SUBSET of input, so a skill payload
    sent once and then cached must not be billed at full rate in our reporting."""
    m = hm.read_usage(store)
    assert m["tokens_cache_read"] == 9300
    assert m["tokens_fresh_input"] == 11000 - 9300
    assert m["cache_read_share_pct"] == pytest.approx(9300 / 11000 * 100, abs=0.01)


def test_turns_counts_distinct_turns_not_requests(store):
    """A subagent request shares its parent's turn index; counting requests as
    turns would overstate how many round trips the task needed."""
    m = hm.read_usage(store)
    assert m["agent_requests"] == 3
    assert m["agent_turns"] == 2


def test_model_identity_is_captured_as_numeric_metrics(store):
    metrics = hm.read_usage(store)
    assert metrics["model_count"] == 1
    encoded = {
        key: value for key, value in metrics.items() if key.startswith("model_ids_")
    }
    assert encoded["model_ids_available"] == 1
    assert all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in encoded.values()
    )
    assert all(
        value < 2**53
        for key, value in encoded.items()
        if "_chunk_" in key
    )


def test_multiple_models_are_recorded_not_silently_merged(tmp_path):
    mixed = _make_store(
        tmp_path,
        [
            _row(turn_index=0, model="model-a"),
            _row(turn_index=1, model="model-b"),
        ],
    )
    metrics = hm.read_usage(mixed)
    assert metrics["model_count"] == 2


# ---------------------------------------------------------------------------
# missing data must not read as zero cost
# ---------------------------------------------------------------------------
def test_missing_store_is_flagged_not_zeroed(tmp_path):
    metrics = hm.build_metrics(
        None, _ctrf(tmp_path, []), _reward(tmp_path, 0)
    )
    assert metrics["tokens_available"] == 0
    assert "tokens_input" not in metrics, (
        "A failed harvest must OMIT token metrics, not report 0. A silent zero "
        "would drag down every average computed over it."
    )


def test_present_store_is_flagged_available(store, tmp_path):
    metrics = hm.build_metrics(store, _ctrf(tmp_path, []), _reward(tmp_path, 1))
    assert metrics["tokens_available"] == 1
    assert metrics["tokens_input"] > 0


# ---------------------------------------------------------------------------
# outcome gating
# ---------------------------------------------------------------------------
def test_failed_run_reports_no_cost_to_green(store, tmp_path):
    """Otherwise an agent that gives up early looks like the cheapest one."""
    metrics = hm.build_metrics(store, _ctrf(tmp_path, []), _reward(tmp_path, 0))
    assert metrics["reward"] == 0
    for key in ("credits_to_green", "turns_to_green", "billable_tokens_to_green"):
        assert key not in metrics


def test_green_run_reports_cost_to_green(store, tmp_path):
    metrics = hm.build_metrics(store, _ctrf(tmp_path, []), _reward(tmp_path, 1))
    assert metrics["reward"] == 1
    assert metrics["credits_to_green"] == pytest.approx(6.0)
    assert metrics["turns_to_green"] == 2
    # billable = fresh input + output, NOT raw input
    assert metrics["billable_tokens_to_green"] == 1700 + 350


def test_missing_reward_file_counts_as_failure(store, tmp_path):
    metrics = hm.build_metrics(store, _ctrf(tmp_path, []), tmp_path / "nope.txt")
    assert metrics["reward"] == 0


# ---------------------------------------------------------------------------
# CTRF category breakdown — what makes the cost numbers actionable
# ---------------------------------------------------------------------------
def test_check_categories_are_broken_out(tmp_path):
    ctrf = _ctrf(tmp_path, [
        {"name": "/verifier/check_api.py::test_a", "status": "passed"},
        {"name": "/verifier/check_api.py::test_b", "status": "failed"},
        {"name": "/verifier/check_engine.py::test_c", "status": "passed"},
        {"name": "/verifier/check_behavior.py::test_d", "status": "passed"},
    ])
    m = hm.read_ctrf(ctrf)
    assert m["checks_total"] == 4
    assert m["checks_passed"] == 3
    assert m["checks_failed"] == 1
    assert m["checks_api_passed"] == 1 and m["checks_api_total"] == 2
    assert m["checks_engine_passed"] == 1
    assert m["checks_behavior_passed"] == 1


def test_skipped_checks_are_excluded_from_totals(tmp_path):
    """A skipped check was not graded. Counting it as a pass would inflate the
    score; counting it as a failure would punish a legitimately N/A rule."""
    ctrf = _ctrf(tmp_path, [
        {"name": "/verifier/check_api.py::test_a", "status": "passed"},
        {"name": "/verifier/check_source.py::test_b", "status": "skipped"},
    ])
    m = hm.read_ctrf(ctrf)
    assert m["checks_total"] == 1
    assert "checks_source_total" not in m


def test_malformed_ctrf_does_not_crash_the_harvest(tmp_path):
    """Losing telemetry must never change a grading outcome."""
    bad = tmp_path / "ctrf.json"
    bad.write_text("not json")
    assert hm.read_ctrf(bad) == {}


# ---------------------------------------------------------------------------
# MSBench output contract
# ---------------------------------------------------------------------------
def test_all_emitted_values_are_numeric(store, tmp_path):
    """MSBench infers a `numeric` schema from the values and validates that the
    schema is consistent across instances. A single string would break it."""
    metrics = hm.build_metrics(store, _ctrf(tmp_path, [
        {"name": "/verifier/check_api.py::t", "status": "passed"},
    ]), _reward(tmp_path, 1))
    bad = {k: v for k, v in metrics.items()
           if not isinstance(v, (int, float)) or isinstance(v, bool)}
    assert not bad, f"non-numeric custom metrics would break MSBench's schema: {bad}"


def test_writes_custom_metrics_json_to_the_output_dir(store, tmp_path):
    out = tmp_path / "output"
    rc = hm.main([
        "--store", str(store),
        "--ctrf", str(_ctrf(tmp_path, [])),
        "--reward", str(_reward(tmp_path, 1)),
        "--output-dir", str(out),
    ])
    assert rc == 0
    written = json.loads((out / "custom_metrics.json").read_text())
    assert written["reward"] == 1
    assert written["tokens_available"] == 1


def test_existing_metrics_are_merged_not_clobbered(store, tmp_path):
    """The agent may have written its own metrics to the same file; destroying
    them would lose data MSBench expects to ingest."""
    out = tmp_path / "output"
    out.mkdir()
    (out / "custom_metrics.json").write_text(json.dumps({"Tool_Calls_Total": 56}))
    hm.main([
        "--store", str(store),
        "--ctrf", str(_ctrf(tmp_path, [])),
        "--reward", str(_reward(tmp_path, 1)),
        "--output-dir", str(out),
    ])
    written = json.loads((out / "custom_metrics.json").read_text())
    assert written["Tool_Calls_Total"] == 56
    assert written["tokens_available"] == 1


def test_reader_does_not_mutate_the_session_store(store):
    """The store may be live. Snapshot, never open it for writing."""
    before = store.read_bytes()
    hm.read_usage(store)
    assert store.read_bytes() == before


# ---------------------------------------------------------------------------
# report generator (MSBench Skill-Efficacy Benchmark effectiveness report)
# ---------------------------------------------------------------------------
import importlib.util as _ilu
from pathlib import Path as _Path

# tests/ -> benchmark-metrics/ -> scenarios/ -> testing/ -> repo root
_REPORT_PY = (_Path(__file__).resolve().parents[4]
              / "benchmarks" / "documentdb-sdk-skills" / "report.py")


def _report_mod():
    spec = _ilu.spec_from_file_location("_report", _REPORT_PY)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _msbench_report(benchmark, resolved, values_by_instance):
    """Shape mirrors `msbench-cli report --output <f>.json` (msbench.report 2.0)."""
    return {
        "schema": {"id": "msbench.report", "version": "2.0.0"},
        "resolved": {benchmark: resolved},
        "custom_metrics": {
            benchmark: {k: {"values": v} for k, v in values_by_instance.items()}
        },
    }


def _model_values(model="m1"):
    return hm.encode_text_metrics("model_ids", model)


def test_report_counts_only_true_as_a_pass():
    """`resolved` values may be bool OR the string "error". Counting "error" as
    anything but a failure would silently inflate the published pass rate."""
    m = _report_mod()
    rep = _msbench_report(
        "documentdb-sdk-skills",
        {"a": True, "b": False, "c": "error"},
        {"a": {"tokens_available": 1}, "b": {"tokens_available": 1},
         "c": {"tokens_available": 1}},
    )
    s = m.summarise(rep, "documentdb-sdk-skills")
    assert s["instances"] == 3
    assert s["passed"] == 1
    assert s["pass_rate"] == pytest.approx(1 / 3)


def test_report_flags_instances_with_no_token_data():
    """A missing cost figure must be visible, not averaged in as zero."""
    m = _report_mod()
    rep = _msbench_report(
        "documentdb-sdk-skills",
        {"a": True, "b": True},
        {"a": {"tokens_available": 1, "ai_credits": 10.0},
         "b": {"tokens_available": 0}},
    )
    s = m.summarise(rep, "documentdb-sdk-skills")
    assert s["missing_token_data"] == 1
    # the mean is over the ONE instance that reported, not diluted by a zero
    assert s["cost"]["ai_credits"] == pytest.approx(10.0)
    assert s["cost_n"]["ai_credits"] == 1


def test_report_requires_both_arms():
    """A one-armed report is uninterpretable: an absolute pass rate cannot
    distinguish an effective kit from an easy task."""
    m = _report_mod()
    with pytest.raises(SystemExit):
        m.main(["--treatment", str(_REPORT_PY)])  # no --control


def test_report_decodes_the_exact_observed_model():
    m = _report_mod()
    values = _model_values("claude-opus-5")
    assert m.decode_text_metrics(values, "model_ids") == "claude-opus-5"


def test_report_rejects_missing_model_provenance():
    m = _report_mod()
    treatment = m.summarise(
        _msbench_report(
            "documentdb-sdk-skills",
            {"a": True},
            {"a": {"tokens_available": 1}},
        ),
        "documentdb-sdk-skills",
    )
    control_values = {"tokens_available": 1, **_model_values("m1")}
    control = m.summarise(
        _msbench_report(
            "documentdb-sdk-skills-noskills",
            {"a": True},
            {"a": control_values},
        ),
        "documentdb-sdk-skills-noskills",
    )
    with pytest.raises(SystemExit, match="missing observed model provenance"):
        m.require_comparable_model_provenance(treatment, control)


def test_report_rejects_different_models_between_arms():
    m = _report_mod()
    treatment = m.summarise(
        _msbench_report(
            "documentdb-sdk-skills",
            {"a": True},
            {"a": {"tokens_available": 1, **_model_values("model-a")}},
        ),
        "documentdb-sdk-skills",
    )
    control = m.summarise(
        _msbench_report(
            "documentdb-sdk-skills-noskills",
            {"a": True},
            {"a": {"tokens_available": 1, **_model_values("model-b")}},
        ),
        "documentdb-sdk-skills-noskills",
    )
    with pytest.raises(SystemExit, match="different models"):
        m.require_comparable_model_provenance(treatment, control)


def test_report_accepts_the_same_observed_model():
    m = _report_mod()
    values = {"tokens_available": 1, **_model_values("gpt-5.6-sol")}
    treatment = m.summarise(
        _msbench_report("documentdb-sdk-skills", {"a": True}, {"a": values}),
        "documentdb-sdk-skills",
    )
    control = m.summarise(
        _msbench_report(
            "documentdb-sdk-skills-noskills", {"a": True}, {"a": values}
        ),
        "documentdb-sdk-skills-noskills",
    )
    assert (
        m.require_comparable_model_provenance(treatment, control)
        == "gpt-5.6-sol"
    )


def test_credits_per_passing_result_charges_failures_to_successes(tmp_path):
    """5 runs at 100 credits with 1 pass costs 500 per success, not 100."""
    m = _report_mod()
    rep = _msbench_report(
        "documentdb-sdk-skills",
        {f"i{n}": (n == 0) for n in range(5)},
        {f"i{n}": {"tokens_available": 1, "ai_credits": 100.0} for n in range(5)},
    )
    s = m.summarise(rep, "documentdb-sdk-skills")
    ctl = m.summarise(
        _msbench_report("documentdb-sdk-skills-noskills",
                        {"i0": True},
                        {"i0": {"tokens_available": 1, "ai_credits": 100.0}}),
        "documentdb-sdk-skills-noskills")
    m.render(s, ctl)  # populates _cpp
    assert s["_cpp"] == pytest.approx(500.0)


def test_report_renders_the_headline_and_category_tables():
    m = _report_mod()
    t = m.summarise(_msbench_report(
        "documentdb-sdk-skills", {"a": True},
        {"a": {"tokens_available": 1, "ai_credits": 5.0,
               **_model_values("m1"),
               "checks_engine_passed": 4, "checks_engine_total": 4}}),
        "documentdb-sdk-skills")
    c = m.summarise(_msbench_report(
        "documentdb-sdk-skills-noskills", {"a": False},
        {"a": {"tokens_available": 1, "ai_credits": 4.0,
               **_model_values("m1"),
               "checks_engine_passed": 0, "checks_engine_total": 4}}),
        "documentdb-sdk-skills-noskills")
    out = m.render(t, c)
    assert "Pass rate" in out
    assert "`engine`" in out
    assert "Credits per passing result" in out
    assert "Observed model identifier" in out
    # the reader must be steered away from raw input tokens
    assert "fresh" in out.lower()
