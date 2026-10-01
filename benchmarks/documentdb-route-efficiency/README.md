# Route efficiency: text skills vs diagnostic scripts

## The two arms

The intervention is **which route the kit exposes**, and nothing else.

| | Control — `route-text` | Treatment — `route-script` |
|---|---|---|
| `~/.copilot/skills/` | the kit's **text skills** | *(empty)* |
| `scripts/`, `knowledge-base/` | **absent** | **present** |
| How it answers | reads a `SKILL.md`, runs its own `mongosh` / `psql`, interprets raw output | routes with `kb-route.sh`, runs one read-only script, reads the compact verdict |
| Database | identical fixture | identical fixture |
| Question asked | identical | identical |

Both arms are told the same thing and neither is told which route it has. The
arm is expressed purely by what exists on disk — `shared/arms/install-arm.sh`.

### Why not "agent chooses"?

A third design — install both and see which it picks — measures something
different and more realistic, but it cannot answer *this* question: it would
confound "how expensive is each route" with "how good is the agent at choosing".
Worth doing later as a separate task; it is not this one.

---

## Preventing leakage

Leakage would flatter whichever arm runs second, so every shared surface is
reset. This is the part most easily got wrong.

| Leak | Why it matters here | Control |
|---|---|---|
| **Conversation history** | a second run could answer from the first run's reasoning | one fresh agent session per run; no multi-turn reuse across runs |
| **Prompt cache** | a warm cache makes the same payload cost far less | arm order is **randomised per iteration**, so warmth cannot systematically favour one arm |
| **Database state** | `$indexStats` / `idx_scan` counters accumulate; `index-redundancy-finder`'s *unused* findings depend on them | **a fresh database per run**, uniquely named, seeded from the same deterministic fixture |
| **Planner statistics** | stale stats flip query plans (this caused a real 2-in-7 flake in Diagnostic Regression Suite) | `ANALYZE` after every seed |
| **Filesystem** | a leftover script or `SKILL.md` silently converts one arm into the other | the arm installer **deletes the other route** and asserts it is gone |
| **Answer file** | a stale `/output/finding.json` would be graded as this run's answer | removed before each run |

The database point is the one that would most easily go unnoticed: run the
script arm first and it warms the index counters, so the text arm's *correct*
answer changes. Same fixture, fresh database, every time.

---

## What is measured

### 1. Parity — graded first, and it gates everything

Both arms must reach the **same finding**. A route that is cheap because it
answers *worse* is not a saving, and reporting its token count as one would be
actively misleading.

Each arm writes `/output/finding.json`:

```json
{
  "redundant_indexes": ["tenant_id_1"],
  "reason": "prefix of tenant_id_1_status_1"
}
```

The verifier compares that against `expected-findings.yaml` — **structurally, no
judge**. The finding is a fact about the database, so it is checkable exactly.

### 2. Cost — reported only for runs that achieved parity

`tokens_fresh_input`, `tokens_output`, `ai_credits`, `agent_turns`, harvested
from the Copilot CLI session store by the same
[`harvest_metrics.py`](../documentdb-sdk-skills/shared/verifier/harvest_metrics.py)
the SDK-skills benchmark uses, so the two benchmarks cannot report cost
differently.

**The headline is cost conditional on parity.** Comparing tokens across runs
where one arm got the wrong answer compares nothing.

---

## Cross-model, and why cost is in USD

**Tokens are not comparable across models.** Measured against published rates,
output differs 2.5x between Gemini 3.1 Pro ($12/MTok) and GPT-5.6 Sol ($30/MTok),
and input 2.5x ($2 vs $5). A cross-model table in raw tokens would rank
tokenisers and verbosity, not cost. `shared/verifier/pricing.py` converts each
run at its own model's published rate, itemising fresh input, cache reads
(~90% cheaper) and output.

Cross-checked against a second, independent source: Copilot's `total_nano_aiu`
is token-based per-model billing at 1 credit = $0.01, and the two agree within
~3% (gemini 1.000, opus-5 0.995, opus-4.8 0.985, sol 0.968). A test fails if
they ever diverge, which would mean either the rate table has gone stale or
billing changed.

## Running it: subagents, no extra credential

The cross-model matrix was thought to need `COPILOT_SDK_AUTH_TOKEN`. It does
not. The Copilot CLI's own subagents supply the three properties this
experiment needs:

| Requirement | How a subagent satisfies it |
|---|---|
| clean context per run | each subagent has its own context window — structural, not cleanup |
| model selection | pinned per subagent |
| per-run attribution | usage lands in `assistant_usage_events` with a distinct non-null `agent_id`, exactly one model each |

Verified with a probe pinned to `gemini-3.1-pro-preview`: one row,
`agent_id=toolu_01MYbS4…`, 6,867 in / 3 out, $0.01377 — matching the 1.377
credits Copilot recorded. The orchestrating parent's rows carry
`agent_id=NULL` and are excluded.

```bash
python3 shared/verifier/attribute.py snapshot      # -> <id>
#   ... launch subagents, one per (model, arm) ...
python3 shared/verifier/attribute.py collect --since <id> --out results/raw/runs.json
python3 shared/verifier/pricing.py results/raw/runs.json
```

**What this harness is not:** a subagent is not the MSBench or Vally executor —
different scaffolding, system prompt and tool surface. Absolute numbers are not
comparable to an MSBench run. They are comparable *within* this harness, which
is all a cross-model or cross-arm comparison needs.

## Status

⬜ **Not yet run end-to-end.** Attribution, pricing, arms, fixture and the
parity grader are built and validated; the subagent path removes the credential
blocker. See [`results/`](results/).
