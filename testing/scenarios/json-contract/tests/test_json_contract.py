"""Shape guard for every diagnostic script's --json output.

Dataset-agnostic: asserts JSON validity + top-level/nested structure and that
--json stdout is pure JSON. Never asserts specific finding counts. The per-script
contract is read from expected-findings.yaml so it stays data-driven.
"""

from pathlib import Path

import pytest
import yaml

import kit

# Load the shape contract at collection time so we can parametrize over scripts.
_SPEC = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "expected-findings.yaml").read_text()
)
SHAPE = _SPEC["shape"]
TYPEMAP = {"list": list, "object": dict}
ADVERSARIAL_COLLECTION = (
    "safe;db.getCollection('diagnostic_sentinel').drop();db.safe"
)


@pytest.fixture(scope="session")
def json_outputs(seeded_db):
    """Run every script once with --json; return {script: ScriptResult}."""
    out = {}
    for script in SHAPE:
        out[script] = kit.run_script(script, "--db", seeded_db, "--json",
                                     want_json=True)
    return out


@pytest.fixture(scope="session")
def quoted_database(request, require_container):
    name = "test_json_'contract"
    fixture = Path(__file__).resolve().parents[1] / "fixture.js"
    kit.drop_db(name, container=require_container)
    kit.seed(name, fixture, container=require_container)
    yield name
    if not request.config.getoption("--keep-db"):
        kit.drop_db(name, container=require_container)


@pytest.mark.jsoncontract
@pytest.mark.parametrize("script", list(SHAPE))
def test_emits_valid_json_of_expected_shape(json_outputs, script):
    res = json_outputs[script]
    assert res.returncode == 0, (
        f"{script} --json failed (rc={res.returncode})\n{res.stderr[:400]}"
    )
    assert res.json is not None, (
        f"{script} --json did not emit parseable JSON:\n{res.stdout[:400]}"
    )
    exp = SHAPE[script]
    want = TYPEMAP[exp["type"]]
    assert isinstance(res.json, want), (
        f"{script}: expected top-level {exp['type']}, got {type(res.json).__name__}"
    )
    for key in exp.get("keys", []):
        assert key in res.json, f"{script}: missing required top-level key '{key}'"


@pytest.mark.jsoncontract
def test_json_stdout_is_pure_json(json_outputs):
    """--json stdout must be ONLY JSON — no box headers, no psql SET tags."""
    for script, res in json_outputs.items():
        s = res.stdout.strip()
        assert s and s[0] in "{[", f"{script}: stdout is not JSON: {s[:80]!r}"
        for leak in ("╔", "═", "LAYER", "\nSET", "CHECK "):
            assert leak not in res.stdout, (
                f"{script}: non-JSON leakage {leak!r} in --json stdout"
            )


@pytest.mark.jsoncontract
@pytest.mark.parametrize("script", list(SHAPE))
def test_bash_and_portable_entry_points_have_same_json_shape(
    json_outputs, seeded_db, script
):
    portable = json_outputs[script]
    bash = kit.run_script(
        script,
        "--db",
        seeded_db,
        "--json",
        want_json=True,
        portable=False,
    )
    assert bash.returncode == 0, (
        f"{script} Bash entry point failed (rc={bash.returncode})\n"
        f"{bash.stderr[:400]}"
    )
    assert bash.json is not None, (
        f"{script} Bash entry point emitted invalid JSON:\n{bash.stdout[:400]}"
    )
    assert type(bash.json) is type(portable.json)
    if isinstance(portable.json, dict):
        assert set(bash.json) == set(portable.json)


@pytest.mark.jsoncontract
@pytest.mark.parametrize(
    ("script", "extra_args"),
    [
        ("document-bloat-advisor.sh", []),
        (
            "toast-split-advisor.sh",
            ["--collection", ADVERSARIAL_COLLECTION, "--sample", "5"],
        ),
    ],
)
def test_catalog_names_are_passed_as_data(quoted_database, script, extra_args):
    result = kit.run_script(
        script,
        "--db",
        quoted_database,
        "--min-total-kb",
        "0",
        "--toast-ratio",
        "0",
        *extra_args,
        "--json",
        want_json=True,
        portable=False,
    )
    assert result.returncode == 0, (
        f"{script} failed for a quoted collection name:\n{result.stderr[:400]}"
    )
    assert result.json is not None, result.stdout[:400]
    findings = (
        result.json
        if script == "document-bloat-advisor.sh"
        else result.json["findings"]
    )
    quoted = [
        finding for finding in findings
        if finding["collection"] == ADVERSARIAL_COLLECTION
    ]
    assert quoted, f"{script} did not preserve the exact collection name"
    assert quoted[0]["avg_obj_size"] > 0, (
        f"{script} did not sample the quoted collection"
    )
    sentinel = kit.mongosh_eval(
        quoted_database,
        'db.getCollection("diagnostic_sentinel").countDocuments({})',
    )
    assert "1" in sentinel.split(), (
        f"{script} executed JavaScript embedded in the collection name"
    )


@pytest.mark.jsoncontract
def test_perf_advisor_nested_shape(json_outputs):
    d = json_outputs["perf-advisor.sh"].json
    assert isinstance(d["mongo"], list) and d["mongo"], "perf: mongo[] is empty"
    m = d["mongo"][0]
    for key in ("collections", "index_health", "collscans",
                "query_timings", "slow_queries", "summary"):
        assert key in m, f"perf mongo[0] missing '{key}'"
    # query_timings is the deterministic view (every probe); slow_queries is the
    # threshold-filtered subset of it, so it can never be the larger of the two.
    assert len(m["slow_queries"]) <= len(m["query_timings"]), (
        "perf: slow_queries must be a subset of query_timings"
    )
    assert isinstance(d["pg"], dict), "perf: pg is not an object"
    for key in ("config", "cache_top", "scan_mix", "unused_pg_indexes", "blocked_queries"):
        assert key in d["pg"], f"perf pg missing '{key}'"


@pytest.mark.jsoncontract
def test_data_integrity_nested_shape(json_outputs):
    d = json_outputs["data-integrity-check.sh"].json
    for side in ("referential_integrity", "type_consistency"):
        assert "issues" in d[side], f"integrity {side} missing 'issues'"
        assert "findings" in d[side], f"integrity {side} missing 'findings'"
        assert isinstance(d[side]["findings"], list)
    assert isinstance(d["ok"], bool), "integrity 'ok' must be a boolean"
    assert isinstance(d["total_issues"], int), "integrity 'total_issues' must be an int"
