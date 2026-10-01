"""Determinism contract (Diagnostic Regression Suite) — the deterministic half of the kit's testing.

The diagnostic scripts are *tools*, not agents: given the same database state
they must return the same answer every time. This scenario runs each script
N times (N from expected-findings.yaml) and asserts the canonicalised `--json`
results are identical.

Three traps this suite is explicitly designed to avoid:

1. **False determinism** — a script that finds nothing is identical every run.
   `must_find` asserts the output is non-empty, so the comparison is meaningful.
2. **Over-broad normalisation** — the volatile-field allowlist is small,
   measured, and documented in expected-findings.yaml. Drift outside it fails.
3. **A test that cannot fail** — `test_injected_drift_is_detected` is a negative
   control proving the comparison actually catches a difference.
"""

from pathlib import Path

import pytest
import yaml

import kit
from canonicalise import canonical_json, canonicalise, is_empty_result

_SPEC = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "expected-findings.yaml").read_text()
)
RUNS = _SPEC["runs"]
SCRIPTS = _SPEC["scripts"]
VOLATILE = _SPEC["volatile_fields"]
ORDER_INSENSITIVE = _SPEC.get("order_insensitive_lists", [])
SAMPLED_MAPS = _SPEC.get("sampled_count_maps", [])
SAMPLED_SIZES = _SPEC.get("sampled_size_strings", [])
SCRIPT_IDS = [s["name"] for s in SCRIPTS]


@pytest.fixture(scope="session")
def repeated_runs(seeded_db):
    """Run every script RUNS times against the same, untouched database.

    Nothing else touches the database between runs, so any difference is the
    script's own nondeterminism.
    """
    results = {}
    for spec in SCRIPTS:
        name = spec["name"]
        results[name] = [
            kit.run_script(name, "--db", seeded_db, "--json", want_json=True)
            for _ in range(RUNS)
        ]
    return results


@pytest.mark.determinism
@pytest.mark.parametrize("script", SCRIPT_IDS)
def test_script_output_is_deterministic(repeated_runs, script):
    """Same DB state -> identical canonicalised --json across N runs."""
    runs = repeated_runs[script]

    for i, r in enumerate(runs):
        assert r.returncode == 0, (
            f"{script} run {i + 1} exited {r.returncode}\nstderr: {r.stderr[:400]}"
        )
        assert r.json is not None, (
            f"{script} run {i + 1} did not emit valid JSON.\n"
            f"stdout[:400]: {r.stdout[:400]}"
        )

    baseline = canonical_json(runs[0].json, VOLATILE, ORDER_INSENSITIVE, SAMPLED_MAPS, SAMPLED_SIZES)
    for i, r in enumerate(runs[1:], start=2):
        current = canonical_json(r.json, VOLATILE, ORDER_INSENSITIVE, SAMPLED_MAPS, SAMPLED_SIZES)
        if current != baseline:
            import difflib

            diff = "\n".join(
                list(
                    difflib.unified_diff(
                        baseline.splitlines(),
                        current.splitlines(),
                        fromfile="run 1",
                        tofile=f"run {i}",
                        lineterm="",
                    )
                )[:40]
            )
            pytest.fail(
                f"{script} is NOT deterministic: run 1 and run {i} differ after "
                f"canonicalisation.\n"
                f"Either the script has a real nondeterminism bug, or a new live "
                f"measurement needs adding to `volatile_fields` in "
                f"expected-findings.yaml (review it — do not grow the list "
                f"silently).\n\n{diff}"
            )


@pytest.mark.determinism
@pytest.mark.parametrize(
    "script", [s["name"] for s in SCRIPTS if s.get("must_find")]
)
def test_findings_are_non_empty(repeated_runs, script):
    """Guard against 'false determinism' — an empty result proves nothing."""
    canonical = canonicalise(repeated_runs[script][0].json, VOLATILE, ORDER_INSENSITIVE, SAMPLED_MAPS, SAMPLED_SIZES)
    assert not is_empty_result(canonical), (
        f"{script} produced an EMPTY result on the determinism fixture, so its "
        f"determinism assertion is vacuous. Fix fixture.js to plant a finding "
        f"this script detects, or set must_find: false with a reason."
    )


@pytest.mark.determinism
def test_injected_drift_is_detected():
    """Negative control: the comparison must actually be able to fail.

    A determinism test that can never fail is worse than none at all.
    """
    a = {"findings": [{"collection": "accounts", "rule": "PREFIX_REDUNDANT"}]}
    b = {"findings": [{"collection": "accounts", "rule": "EXACT_DUPLICATE"}]}
    assert canonical_json(a, VOLATILE, ORDER_INSENSITIVE, SAMPLED_MAPS, SAMPLED_SIZES) != canonical_json(
        b, VOLATILE, ORDER_INSENSITIVE, SAMPLED_MAPS, SAMPLED_SIZES
    ), "canonicalisation is too aggressive — it erased a real difference"


@pytest.mark.determinism
def test_volatile_normalisation_is_targeted():
    """The allowlist must remove live measurements — and nothing structural."""
    payload = {
        "collection": "orders",
        "rule": "PREFIX_REDUNDANT",
        "ms": 57,
        "scan_mix": [{"collection": "b", "seq_scan": 9}, {"collection": "a", "seq_scan": 1}],
    }
    out = canonicalise(payload, VOLATILE, ORDER_INSENSITIVE, SAMPLED_MAPS, SAMPLED_SIZES)

    # volatile values removed ...
    assert "ms" not in out
    assert all("seq_scan" not in entry for entry in out["scan_mix"])
    # ... structural facts preserved ...
    assert out["collection"] == "orders"
    assert out["rule"] == "PREFIX_REDUNDANT"
    # ... and volatile ordering normalised (a before b, regardless of input order)
    assert [e["collection"] for e in out["scan_mix"]] == ["a", "b"]


@pytest.mark.determinism
def test_sampled_counts_normalised_but_finding_preserved():
    """`$sample`-derived counts are blanked; the categories (the finding) survive.

    `data-integrity-check.sh` samples documents to detect mixed field types, so
    the counts wobble run to run. What matters — that `amount` holds BOTH a
    number and a string — must still be asserted, and a *different* set of
    categories must still be detected as a difference.
    """
    run1 = {"field": "amount", "types": {"number": 87, "string": 13}}
    run2 = {"field": "amount", "types": {"number": 85, "string": 15}}
    same_finding_diff_counts = {"types"}
    assert canonical_json(run1, VOLATILE, ORDER_INSENSITIVE, same_finding_diff_counts) == \
        canonical_json(run2, VOLATILE, ORDER_INSENSITIVE, same_finding_diff_counts)

    # but a genuinely different set of types is still caught
    run3 = {"field": "amount", "types": {"number": 100}}
    assert canonical_json(run1, VOLATILE, ORDER_INSENSITIVE, same_finding_diff_counts) != \
        canonical_json(run3, VOLATILE, ORDER_INSENSITIVE, same_finding_diff_counts)
