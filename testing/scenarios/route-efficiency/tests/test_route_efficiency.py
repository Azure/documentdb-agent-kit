"""Guards for the route-efficiency benchmark (text skills vs diagnostic scripts).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

import kit

pytestmark = pytest.mark.routeefficiency

BENCH = kit.REPO_DIR / "benchmarks" / "documentdb-route-efficiency"
TASK = BENCH / "tasks" / "index-redundancy-diagnosis"
sys.path.insert(0, str(BENCH / "shared" / "verifier"))
import check_parity  # noqa: E402


@pytest.fixture(scope="module")
def expected():
    return yaml.safe_load((TASK / "expected-findings.yaml").read_text())


# ---------------------------------------------------------------------------
# arm design
# ---------------------------------------------------------------------------
def test_arms_are_mutually_exclusive_and_asserted():
    """A leftover file turns one arm into the other, and the run would still
    complete and still report a number — a confident comparison of an arm
    against itself. The installer must verify, not just copy."""
    script = (BENCH / "shared" / "arms" / "install-arm.sh").read_text()
    assert "route-text" in script and "route-script" in script
    assert "rm -rf" in script, "the installer must clear the previous arm"
    assert script.count("FATAL") >= 3, (
        "the installer must fail loudly when an arm is contaminated or empty"
    )
    assert "exit 1" in script


def test_instruction_does_not_reveal_the_route():
    """Both arms get the identical prompt. Naming a script or a skill would
    steer one arm and turn the comparison into instruction-following."""
    text = (TASK / "instruction.md").read_text().lower()
    for leak in ("kb-route", "script", "skill", "toolbox", "advisor", "finder"):
        assert leak not in text, f"instruction leaks the route: {leak!r}"


def test_harness_refuses_to_fabricate_runs():
    """Without an agent the harness must stop, not emit plausible numbers.

    A silent fallback here would produce something that looks like a
    measurement and is not — worse than producing nothing.
    """
    script = (BENCH / "run-comparison.sh").read_text()
    assert "AGENT_CMD is not set" in script
    assert "exit 2" in script


def test_harness_resets_every_shared_surface():
    """Each of these is a leak that would favour whichever arm ran second."""
    script = (BENCH / "run-comparison.sh").read_text()
    assert "drop_db" in script, "each run needs its own database"
    assert "ANALYZE" in script, "planner statistics must be settled after seeding"
    assert "arm_order" in script, "arm order must be randomised across iterations"
    assert 'rm -rf "$run_out"' in script, "a stale finding.json must not be graded"


def test_fixture_is_deterministic():
    """Both arms must see byte-identical data, or a cost difference could be a
    data difference."""
    # Strip comments first: the fixture's own docstring says "no Math.random()",
    # and matching that would be a false positive — the check must look at code.
    src = (TASK / "fixture.js").read_text()
    code = "\n".join(line.split("//")[0] for line in src.splitlines())
    assert "Math.random" not in code, (
        "fixture uses Math.random(); both arms must see byte-identical data or "
        "a cost difference could be a data difference"
    )


# ---------------------------------------------------------------------------
# parity grading — the gate on every cost number
# ---------------------------------------------------------------------------
def test_parity_accepts_the_correct_finding(expected):
    r = check_parity.grade(
        {"redundant_indexes": ["tenant_id_1", "email_1"],
         "reason": "tenant_id_1 is a prefix of the compound index; "
                   "email_1 duplicates email_unique"},
        expected)
    assert r["parity"] is True, r


def test_parity_rejects_a_missed_finding(expected):
    r = check_parity.grade(
        {"redundant_indexes": ["tenant_id_1"], "reason": "prefix"}, expected)
    assert r["parity"] is False and r["missed"] == ["email_1"]


def test_parity_rejects_naming_a_healthy_index(expected):
    """Over-reporting is not correctness."""
    r = check_parity.grade(
        {"redundant_indexes": ["tenant_id_1", "email_1", "email_unique"],
         "reason": "prefix and duplicate"}, expected)
    assert r["parity"] is False and "email_unique" in r["false_positives"]


def test_parity_rejects_listing_every_index(expected):
    """The obvious attack: an arm could 'win' parity by naming everything."""
    r = check_parity.grade(
        {"redundant_indexes": ["tenant_id_1", "email_1",
                               "tenant_id_1_status_1", "customer_id_1", "_id_"],
         "reason": "prefix duplicate"}, expected)
    assert r["parity"] is False and len(r["false_positives"]) >= 3


def test_parity_requires_a_stated_mechanism(expected):
    """Right names with no reasoning is a lucky guess, not a diagnosis."""
    r = check_parity.grade(
        {"redundant_indexes": ["tenant_id_1", "email_1"],
         "reason": "these should be dropped"}, expected)
    assert r["parity"] is False and r["unjustified"]


def test_parity_tolerates_formatting_differences(expected):
    """Failing over `accounts.tenant_id_1` would grade prose, not correctness."""
    r = check_parity.grade(
        {"redundant_indexes": ["accounts.tenant_id_1", "  EMAIL_1 "],
         "reason": "prefix of the compound index; duplicate key"}, expected)
    assert r["parity"] is True, r


# ---------------------------------------------------------------------------
# cost aggregation
# ---------------------------------------------------------------------------
def _summarizer():
    import importlib.util
    spec = importlib.util.spec_from_file_location("_sum", BENCH / "summarize.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cost_excludes_runs_that_failed_parity():
    """THE headline rule.

    A route that is cheaper because it answered wrong has saved nothing.
    Averaging its tokens in would manufacture a saving out of a failure — and
    the failing run is typically the cheapest, so the bias is large.
    """
    m = _summarizer()
    runs = [
        {"arm": "route-script", "parity": True,  "tokens_available": 1,
         "tokens_fresh_input": 10000, "ai_credits": 10.0},
        {"arm": "route-script", "parity": False, "tokens_available": 1,
         "tokens_fresh_input": 100,   "ai_credits": 0.1},   # wrong AND cheapest
        {"arm": "route-text",   "parity": True,  "tokens_available": 1,
         "tokens_fresh_input": 50000, "ai_credits": 50.0},
    ]
    s = m.summarise(runs)
    assert s["route-script"]["cost"]["tokens_fresh_input"] == 10000, (
        "the parity-failing run was averaged into the cost, inventing a saving"
    )
    assert s["route-script"]["parity_rate"] == pytest.approx(0.5)


def test_missing_token_data_is_excluded_not_zeroed():
    m = _summarizer()
    runs = [
        {"arm": "route-text", "parity": True, "tokens_available": 1,
         "tokens_fresh_input": 40000},
        {"arm": "route-text", "parity": True, "tokens_available": 0},
    ]
    s = m.summarise(runs)
    assert s["route-text"]["cost"]["tokens_fresh_input"] == 40000
    assert s["route-text"]["missing_token_data"] == 1


def test_report_warns_when_the_cheaper_route_is_less_correct():
    """If the script route wins on tokens but loses on correctness, the saving
    must be flagged as suspect rather than published as a win."""
    m = _summarizer()
    runs = [
        {"arm": "route-text", "parity": True, "tokens_available": 1,
         "tokens_fresh_input": 50000, "ai_credits": 50.0},
        {"arm": "route-script", "parity": True, "tokens_available": 1,
         "tokens_fresh_input": 9000, "ai_credits": 9.0},
        {"arm": "route-script", "parity": False, "tokens_available": 1,
         "tokens_fresh_input": 500, "ai_credits": 0.5},
    ]
    out = m.render(m.summarise(runs), runs)
    assert "suspect" in out.lower()


# ---------------------------------------------------------------------------
# cross-model cost in USD
#
# One token of Gemini 3.1 Pro is not one token of GPT-5.6 Sol: output differs
# 2.5x ($12 vs $30 / MTok) and input 2.5x ($2 vs $5). A cross-model table in raw
# tokens would rank tokenisers and verbosity, not cost.
# ---------------------------------------------------------------------------
import pricing  # noqa: E402


def test_every_matrix_model_has_published_pricing():
    """An unpriced model must raise, not fall back to a default rate — a
    guessed rate produces a plausible dollar figure nothing can identify as
    invented."""
    for model in ("claude-opus-5", "gpt-5.6-sol", "gemini-3.1-pro-preview"):
        assert model in pricing.PRICING, f"no pricing for matrix model {model}"
        assert pricing.PRICING[model]["source"].startswith("http")
    with pytest.raises(pricing.UnknownModel):
        pricing.cost_usd({"input_tokens": 1000, "output_tokens": 10}, "no-such-model")


def test_cached_input_is_billed_at_the_discounted_rate():
    """~90% discount on cache reads is why the fresh/cached split matters.

    Billing all input at the full rate would overstate a skill payload's cost
    by roughly 10x, since it is sent once and then read from cache.
    """
    for model in ("claude-opus-5", "gpt-5.6-sol", "gemini-3.1-pro-preview"):
        p = pricing.PRICING[model]
        assert p["cached_input"] < p["input"] / 2, (
            f"{model}: cached input is not discounted"
        )
    all_fresh = pricing.cost_usd(
        {"input_tokens": 1_000_000, "cache_read_tokens": 0, "output_tokens": 0},
        "claude-opus-5")
    all_cached = pricing.cost_usd(
        {"input_tokens": 1_000_000, "cache_read_tokens": 1_000_000, "output_tokens": 0},
        "claude-opus-5")
    assert all_fresh["usd_total"] == pytest.approx(5.00)
    assert all_cached["usd_total"] == pytest.approx(0.50)


def test_models_are_not_interchangeable_on_cost():
    """The reason this module exists: identical usage costs materially
    different amounts, so tokens alone cannot rank models."""
    usage = {"input_tokens": 100_000, "cache_read_tokens": 90_000,
             "output_tokens": 5_000}
    costs = {m: pricing.cost_usd(usage, m)["usd_total"]
             for m in ("claude-opus-5", "gpt-5.6-sol", "gemini-3.1-pro-preview")}
    assert costs["gemini-3.1-pro-preview"] < costs["claude-opus-5"]
    assert costs["claude-opus-5"] < costs["gpt-5.6-sol"]
    spread = max(costs.values()) / min(costs.values())
    assert spread > 1.5, (
        f"identical usage differs by only {spread:.2f}x across models; if that "
        f"is really true the pricing table is probably stale ({costs})"
    )


def test_long_context_tier_is_applied():
    """Both Sol and Gemini reprice the WHOLE request above a threshold, not
    just the overflow. Missing this understates a long run's cost."""
    below = pricing.cost_usd(
        {"input_tokens": 100_000, "cache_read_tokens": 0, "output_tokens": 1000},
        "gemini-3.1-pro-preview")
    above = pricing.cost_usd(
        {"input_tokens": 300_000, "cache_read_tokens": 0, "output_tokens": 1000},
        "gemini-3.1-pro-preview")
    assert below["long_context_tier"] is False
    assert above["long_context_tier"] is True
    assert above["rates_usd_per_mtok"]["input"] > below["rates_usd_per_mtok"]["input"]


def test_pricing_table_records_when_it_was_retrieved():
    """Rates change. A stale table produces wrong dollar figures with no other
    symptom, so the retrieval date must travel with every priced result."""
    assert pricing.PRICING_RETRIEVED
    priced = pricing.cost_usd(
        {"input_tokens": 1000, "output_tokens": 10}, "claude-opus-5")
    assert priced["pricing_retrieved"] == pricing.PRICING_RETRIEVED
    assert priced["pricing_source"].startswith("http")


def test_published_rates_agree_with_copilot_credits():
    """Cross-check against a second, independent cost source.

    Copilot's `total_nano_aiu` is token-based per-model billing at
    1 credit = $0.01. Pricing real usage with the published rates and dividing
    by (credits x $0.01) gives ~1.0 for every model measured. A future
    divergence means either the rate table has gone stale or Copilot changed
    its billing — both worth catching.
    """
    import sqlite3
    store = Path.home() / ".copilot" / "session-store.db"
    if not store.is_file():
        pytest.skip("no local session store to cross-check against")
    conn = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    checked = 0
    try:
        for model in ("claude-opus-5", "gpt-5.6-sol", "gemini-3.1-pro-preview"):
            rows = list(conn.execute(
                "SELECT input_tokens, cache_read_tokens, output_tokens, total_nano_aiu "
                "FROM assistant_usage_events "
                "WHERE model = ? AND total_nano_aiu > 0 LIMIT 100", (model,)))
            if len(rows) < 5:
                continue
            ratios = []
            for inp, cache, out, aiu in rows:
                usd = pricing.cost_usd(
                    {"input_tokens": inp, "cache_read_tokens": cache,
                     "output_tokens": out}, model)["usd_total"]
                credits_usd = (aiu / 1e9) * 0.01
                if credits_usd > 0:
                    ratios.append(usd / credits_usd)
            if not ratios:
                continue
            checked += 1
            median = sorted(ratios)[len(ratios) // 2]
            assert 0.8 < median < 1.25, (
                f"{model}: published rates and Copilot credits disagree by "
                f"{median:.2f}x. Either PRICING is stale (retrieved "
                f"{pricing.PRICING_RETRIEVED}) or billing changed."
            )
    finally:
        conn.close()
    if not checked:
        pytest.skip("not enough local usage rows to cross-check")


def test_prompt_is_actually_passed_to_the_agent():
    """Regression: the harness once built the prompt into a lowercase variable
    while the agent command referenced an uppercase one that was never set.

    Every agent would have received an EMPTY task, `|| true` would have hidden
    it, every run would have failed parity, and the conclusion would have been
    "neither route can do this" — a confident, wholly wrong result from a
    one-character-class typo. Static analysis caught it (SC2034).
    """
    src = (BENCH / "run-comparison.sh").read_text()
    assert 'PROMPT="$(sed' in src, "the prompt must be assigned to PROMPT"
    assert "export PROMPT" in src, "PROMPT must be exported for AGENT_CMD"
    assert '<<<"$PROMPT"' in src, "the prompt must also reach the agent on stdin"
    assert 'if [ -z "$PROMPT" ]' in src, (
        "an empty prompt must abort the run rather than silently grading a "
        "no-op as a failed answer"
    )


def test_no_shell_script_has_lint_findings():
    """CI lints every script under benchmarks/. Keeping this here means a
    finding shows up in the normal test run too, not only in CI."""
    import shutil
    import subprocess
    if not shutil.which("shellcheck"):
        pytest.skip("shellcheck not installed")
    scripts = sorted(str(p) for p in (kit.REPO_DIR / "benchmarks").rglob("*.sh"))
    assert scripts, "no shell scripts found under benchmarks/"
    proc = subprocess.run(["shellcheck", "-e", "SC1091", *scripts],
                          capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, f"shellcheck findings:\n{proc.stdout[:2000]}"
