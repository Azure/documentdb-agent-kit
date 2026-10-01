# Scenario: remediation effect (before/after grading)

**Suite:** Diagnostic Regression Suite
**Grading rung:** *measured before/after delta* — chosen because this scenario's
job is to prove determinism, which a judge cannot do.

## The idea

LLM-as-a-judge is a normal and useful grader, and this kit uses it in Cross-Model Skill Evaluations for
things that are genuinely a matter of degree — is the explanation clear, is the
guidance well-targeted. What it cannot give us is **repeatability**: the same
input can score differently across runs, so a judge is the wrong instrument for
a suite whose whole purpose is to show that the diagnostic scripts return a
stable, reproducible answer.

For diagnostics we happen to have a stronger option available, so we use it:
**the database is the oracle.** This scenario applies the kit's advice and
measures whether the database actually improved — a number, not an opinion.

The rule of thumb across the kit is to pick the strongest criterion the scenario
*allows*, not to avoid judges on principle:

| Situation | Grader |
|---|---|
| The outcome is measurable in the system (plans, counters, result sets) | measure it — this scenario |
| The outcome is structural (an index exists, a key order) | assert it |
| The outcome is irreducibly qualitative (was the advice well explained?) | LLM-as-a-judge, blinded and cross-model (Cross-Model Skill Evaluations) |

Judges are used where they are the right tool; here a measurement was available,
and a measurement is what a determinism proof needs.

## The chain it closes

| Step | Assertion |
|---|---|
| 1. The defect is real | `COLLSCAN`, ≥100× scan amplification, full-collection read |
| 2. The kit diagnoses it | `perf-advisor.sh --json` reports the collection scan |
| 3. The fix is **derived from that output** | field parsed from `collscans[].query`, not hardcoded |
| 4. The plan improves | `IXSCAN`, amplification ≤2×, ≥50× better |
| 5. Results are unchanged | identical `order_id` set before and after |
| 6. Nothing got worse | `index-redundancy-finder.sh` reports no new redundancy |
| 7. The tool agrees | `perf-advisor.sh` no longer reports that scan |

**Step 3 is what makes this a test of the kit rather than a test of PostgreSQL.**
If the `collscans` reporting were removed from `perf-advisor.sh`, this suite
could no longer derive a fix and would fail — which is the correct outcome.

## The metric: scan amplification

`totalDocsExamined / nReturned`.

The obvious metric — "documents examined dropped" — is **wrong on this engine**.
Measured here, DocumentDB's planner picks an index scan even for very
unselective predicates, so raw `examined` mostly reflects how many rows the
query legitimately matches:

| Query | Plan | Examined | Returned |
|---|---|---|---|
| `amount > 490` (selective) | IXSCAN | 760 | 760 |
| `amount > 10` (unselective) | IXSCAN | 19,960 | 19,960 |

Both are healthy — they read only rows they return. Scan amplification captures
that independently of selectivity:

| State | Examined | Returned | Amplification |
|---|---|---|---|
| before (no index) | 20,000 | 10 | **2000×** |
| after (index) | 10 | 10 | **1×** |

It is also exactly the ratio the `documentdb-query-performance-tuning` skill
teaches users to read out of `explain()` — so the test grades the same thing the
documentation does.

## Anti-gaming

An improvement metric alone is trivially gamed: index every field and everything
looks fast. Three guards make that cost something:

- **`index-redundancy-finder.sh` is run as a paired regression guard** — the
  remediation may not introduce structural redundancy (`EXACT_DUPLICATE`,
  `PREFIX_REDUNDANT`, or `REVERSE_VARIANT`). Live-counter findings such as
  `WRITE_TAX` are excluded: a brand-new index can briefly report zero reads
  until asynchronous usage counters propagate, even when `explain()` already
  shows `IXSCAN`.
- **Result sets must be identical** — a faster query returning different rows is
  not a fix.
- **The before-state must genuinely be slow** — otherwise every later assertion
  passes for free.

## Verification performed

A green suite proves nothing unless it can fail. Two mutations were injected:

| Mutation | Result |
|---|---|
| Skip the remediation entirely | **3 tests fail** (plan, amplification, tool-confirms) |
| Game the metric: add `{customer_id}`, `{customer_id,status}`, `{customer_id,status,amount}` | **anti-gaming guard fails** with `PREFIX_REDUNDANT` + `WRITE_TAX` |

## Known limitation

Only defects the local container can actually demonstrate are graded here.
**Index-backed sort and covered queries are excluded**: the DocumentDB gateway
pins the experimental GUCs that enable them (`enableIndexOrderbyPushdown`,
`enableNewCompositeIndexOpClass`, `defaultUseCompositeOpClass`) off per session,
and `ALTER SYSTEM` plus an index rebuild does not change the Mongo-API plan.
Grading advice we cannot demonstrate would be worse than not grading it.

## Run

```bash
export DB_PASSWORD='<your-password>'
cd testing && pytest scenarios/remediation-effect
```
