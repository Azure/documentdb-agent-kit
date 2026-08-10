# Scenario: KB Router Contract

> **Logic guard, not a DB test.** These tests exercise the knowledge-base router
> (`knowledge-base/kb_route.py` + `kb-route.sh`) which is a **pure text layer** —
> no DocumentDB container is required to route a query. They guard that natural-
> language questions resolve to the expected tool and that the scoring rules do
> not silently drift.

## Goal

The router maps a natural-language diagnostic question to the exact agent-kit
script (one hop). It is deterministic keyword/example scoring (stdlib only). This
scenario protects two things:

1. **Routing correctness** — a set of representative questions must resolve to the
   expected tool id (e.g. TOAST/large-document questions → `document-bloat-advisor`).
2. **Scoring transparency** — the additive rules that produce the score stay
   intact, and confident routes clear the `>= 2.0` threshold. Keyword matching
   differs by target space:
   - **Tools (Route A / scripts): 1-gram** — every keyword is split into single
     tokens; each distinct matching query token scores `+1.5`. Recall-favoring
     (harmless over-triggering, since scripts are read-only).
   - **Skills (Route B): phrase-aware** — a multi-word keyword scores `+3.0`
     only as a full-phrase substring, a single-word keyword `+1.5`. Precision is
     kept because routing to the wrong guidance is a real cost.
   - Both spaces then add `+2.5×` example overlap and `+2.0×` one-hop boost.

It also runs the `kb-route.sh` wrapper end-to-end via subprocess to guard the
shell → `kb_route.py` seam (env-var handoff, valid `--json`).

## What the fixture plants

Nothing — the router reads `knowledge-base/kb.json` (the shipped KB). There is no
`fixture.js` and no seeded database.

## Contract

[`expected-findings.yaml`](expected-findings.yaml):
- `routes:` / `skill_routes:` — `{query, tool}` / `{query, skill}` pairs the router must satisfy.
- `min_confident_score` — confident routes must score at least this.
- `skill_phrase_case` — a query matching a multi-word **skill** keyword (skills keep phrase matching).
- `tool_onegram_case` — a query whose multi-word **tool** keyword is matched via its single tokens (tools are 1-gram).
- `unconfident_case` — a vague query that must decline for **skills** (tools intentionally over-trigger).

## Run

```bash
pytest scenarios/kb-router
```
