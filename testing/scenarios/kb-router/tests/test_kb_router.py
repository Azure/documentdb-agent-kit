"""Contract tests for the knowledge-base router (kb_route.py + kb-route.sh).

Container-independent: the router is a pure text layer, so these tests import the
routing engine directly and also exercise the shell wrapper via subprocess. No
seeded database is used.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

import kit

KB_DIR = kit.REPO_DIR / "knowledge-base"
KB_JSON = KB_DIR / "kb.json"
KB_SH = KB_DIR / "kb-route.sh"


def _load_engine():
    """Import knowledge-base/kb_route.py as a module (it has no import-time deps)."""
    spec = importlib.util.spec_from_file_location("kb_route", KB_DIR / "kb_route.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def engine():
    return _load_engine()


@pytest.fixture(scope="session")
def kb():
    with open(KB_JSON) as fh:
        return json.load(fh)


def _route(engine, kb, query):
    """Top (score, tool, hits) for a query."""
    return engine.rank_tools(kb, query)[0]


# ── routing correctness (data-driven from expected-findings.yaml) ───────────
def _route_cases():
    import yaml
    spec = yaml.safe_load((Path(__file__).resolve().parents[1] /
                           "expected-findings.yaml").read_text())
    return [(r["query"], r["tool"]) for r in spec["routes"]]


def _skill_route_cases():
    import yaml
    spec = yaml.safe_load((Path(__file__).resolve().parents[1] /
                           "expected-findings.yaml").read_text())
    return [(r["query"], r["skill"]) for r in spec.get("skill_routes", [])]


@pytest.mark.kbrouter
@pytest.mark.parametrize("query,expected_tool", _route_cases())
def test_query_routes_to_expected_tool(engine, kb, query, expected_tool):
    score, tool, hits = _route(engine, kb, query)
    assert tool["id"] == expected_tool, (
        f"'{query}' routed to '{tool['id']}' (score {score:.2f}), "
        f"expected '{expected_tool}'"
    )


@pytest.mark.kbrouter
def test_confident_routes_clear_threshold(engine, kb, expected):
    thr = expected["min_confident_score"]
    for query, _ in _route_cases():
        score, tool, _ = _route(engine, kb, query)
        assert score >= thr, (
            f"'{query}' scored {score:.2f} for '{tool['id']}', "
            f"below confident threshold {thr}"
        )


# ── Route B (skills) routing correctness ────────────────────────────────────
@pytest.mark.kbrouter
@pytest.mark.parametrize("query,expected_skill", _skill_route_cases())
def test_query_routes_to_expected_skill(engine, kb, query, expected_skill):
    ranked = engine.rank_skills(kb, query)
    assert ranked, "rank_skills returned no skills — is kb.json 'skills[]' populated?"
    score, skill, hits = ranked[0]
    assert skill["id"] == expected_skill, (
        f"'{query}' routed to skill '{skill['id']}' (score {score:.2f}), "
        f"expected '{expected_skill}'"
    )


@pytest.mark.kbrouter
def test_confident_skill_routes_clear_threshold(engine, kb, expected):
    thr = expected["min_confident_score"]
    for query, _ in _skill_route_cases():
        score, skill, _ = engine.rank_skills(kb, query)[0]
        assert score >= thr, (
            f"'{query}' scored {score:.2f} for skill '{skill['id']}', "
            f"below confident threshold {thr}"
        )


@pytest.mark.kbrouter
def test_every_registered_skill_points_at_an_existing_skill_md(kb):
    """Each routable skill's `path` must resolve to a real SKILL.md on disk."""
    for sk in kb.get("skills", []):
        p = kit.REPO_DIR / sk["path"]
        assert p.is_file(), f"skill '{sk['id']}' path does not exist: {sk['path']}"


# ── scoring transparency: the multiword-phrase (+3.0) rule ──────────────────
# ── scoring transparency: phrase rule (SKILLS) + 1-gram rule (TOOLS) ────────
@pytest.mark.kbrouter
def test_multiword_phrase_matches_and_scores_for_skills(engine, kb, expected):
    """Skills keep phrase-aware matching: a multi-word skill keyword present as a
    substring scores +3.0 and appears verbatim in the matched keywords."""
    case = expected["skill_phrase_case"]
    score, skill, hits = engine.rank_skills(kb, case["query"])[0]
    assert skill["id"] == case["skill"]
    assert case["keyword"] in hits, (
        f"expected multiword keyword '{case['keyword']}' in matched hits {hits}"
    )
    assert score >= 3.0, f"multiword phrase should score >= 3.0, got {score:.2f}"


@pytest.mark.kbrouter
def test_tool_onegram_matches_constituent_tokens(engine, kb, expected):
    """Tools use 1-gram matching: a multi-word tool keyword is matched via its
    constituent single tokens (the whole phrase is NOT required as a hit)."""
    case = expected["tool_onegram_case"]
    score, tool, hits = _route(engine, kb, case["query"])
    assert tool["id"] == case["tool"], (
        f"'{case['query']}' routed to '{tool['id']}', expected '{case['tool']}'"
    )
    assert case["token"] in hits, (
        f"expected single token '{case['token']}' in matched hits {hits}"
    )
    # hits are single tokens, never multi-word phrases, under 1-gram
    assert all(" " not in h for h in hits), f"1-gram hits must be single tokens: {hits}"


@pytest.mark.kbrouter
def test_gibberish_is_not_confident(engine, kb):
    """A query matching nothing must not produce a confident route."""
    score, _, hits = _route(engine, kb, "qwerty zxcvb asdfg")
    assert score <= 0, f"gibberish scored {score:.2f} with hits {hits}"


@pytest.mark.kbrouter
def test_vague_query_declines_rather_than_guesses(engine, kb, expected):
    """A vague, non-specific query must fall below the confident threshold for
    SKILLS — where routing to the wrong guidance is a real cost, the router
    declines instead of guessing. (Tools intentionally over-trigger under 1-gram
    matching, since running an extra read-only script is harmless.)"""
    query = expected["unconfident_case"]["query"]
    score, skill, _ = engine.rank_skills(kb, query)[0]
    thr = expected["min_confident_score"]
    assert score < thr, (
        f"vague query '{query}' should be below the confident threshold {thr} "
        f"for skills, but scored {score:.2f} for '{skill['id']}'"
    )


# ── shell wrapper end-to-end (guards the bash -> kb_route.py env-var seam) ───
@pytest.mark.kbrouter
def test_shell_wrapper_emits_valid_json(engine, kb):
    p = subprocess.run(
        ["bash", str(KB_SH), "--json", "--db", "mydb",
         "diagnose TOAST detoast overhead"],
        capture_output=True, text=True, timeout=30,
    )
    assert p.returncode == 0, f"kb-route.sh failed: {p.stderr}"
    data = json.loads(p.stdout)  # raises if the wrapper leaked non-JSON
    assert data["match"]["tool"] == "document-bloat-advisor"
    assert data["confident"] is True
    assert data["match"]["command"].startswith("bash scripts/document-bloat-advisor.sh")


@pytest.mark.kbrouter
def test_shell_wrapper_routes_skill_query(engine, kb, expected):
    """A skill-flavoured query must resolve to a skill and be the recommended
    route end-to-end through the shell wrapper."""
    case = expected["skill_shell_case"]
    p = subprocess.run(
        ["bash", str(KB_SH), "--json", case["query"]],
        capture_output=True, text=True, timeout=30,
    )
    assert p.returncode == 0, f"kb-route.sh failed: {p.stderr}"
    data = json.loads(p.stdout)
    assert data["skill_match"] is not None, "expected a skill_match in the output"
    assert data["skill_match"]["skill"] == case["skill"]
    assert data["skill_match"]["open"].endswith("SKILL.md")
    assert data["skill_confident"] is True
    assert data["recommended"] == "skill"


@pytest.mark.kbrouter
def test_shell_wrapper_lists_skills(engine, kb):
    """--skills --json emits the registered skill catalog as valid JSON."""
    p = subprocess.run(
        ["bash", str(KB_SH), "--skills", "--json"],
        capture_output=True, text=True, timeout=30,
    )
    assert p.returncode == 0, f"kb-route.sh --skills failed: {p.stderr}"
    data = json.loads(p.stdout)
    ids = {s["id"] for s in data}
    assert "query-performance-tuning" in ids
    assert len(data) == len(kb.get("skills", []))
