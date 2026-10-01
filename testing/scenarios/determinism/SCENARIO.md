# Scenario: Determinism (Diagnostic Regression Suite)

> **The deterministic half of the kit's testing.** The diagnostic scripts are
> *tools*, not agents: given the same database state they must return the same
> answer every time. This scenario proves that, and fails loudly when they don't.

## Goal

For every diagnostic script, run it **3 times** against one untouched database
and assert the `--json` results are identical after canonicalisation.

Determinism is asserted on `--json` only. The human-readable output deliberately
embeds a wall-clock banner (`Timestamp: …`) and measured latencies, so it is not
byte-stable and is not part of this contract.

## What the fixture plants

[`fixture.js`](fixture.js) seeds `test_determinism` so **every** script produces
non-empty output — otherwise the assertion would be vacuous (see below):

| Collection | Plants | Exercises |
|---|---|---|
| `accounts` | prefix-redundant + duplicate indexes | `index-redundancy-finder.sh` |
| `invoices` | orphaned `account_id` refs, mixed-type `amount` | `data-integrity-check.sh` |
| `articles` | ~6 KB of **incompressible** text per doc | `document-bloat-advisor.sh` |
| `events` | no secondary indexes | `perf-advisor.sh` |
| — | (PG config/cache always reported) | `db-config-advisor.sh` |

Two fixture details that matter:

- **The fixture is itself reproducible.** It uses a fixed-seed Lehmer LCG, never
  `Math.random()` — a determinism scenario cannot be seeded non-deterministically.
- **The large text is incompressible.** PostgreSQL compresses (pglz) before
  storing out of line, so repeated filler text shrinks away and never TOASTs.
  Random-ish characters really do land in TOAST, which is what the bloat advisor
  looks for.

## The three traps this suite avoids

1. **False determinism.** A script that finds *nothing* returns the same empty
   result every run — which proves nothing. `must_find` asserts each script
   actually reported something.
2. **Over-broad normalisation.** The volatile allowlist is small, **measured**
   (not guessed), and documented with the observed drift that justifies each
   entry. Drift outside it fails the test.
3. **A test that cannot fail.** `test_injected_drift_is_detected` is a negative
   control. Verified end-to-end by temporarily emitting `$RANDOM` from
   `db-config-advisor.sh` — the suite failed, as it must.

## Contract

[`expected-findings.yaml`](expected-findings.yaml):

| Key | Meaning |
|---|---|
| `runs` | how many times each script is run (3) |
| `scripts[].must_find` | output must be non-empty (anti-false-determinism) |
| `volatile_fields` | live measurements removed before comparison |
| `order_insensitive_lists` | lists sorted by a volatile metric, so order-normalised |
| `sampled_count_maps` | **now empty** — kept so re-introducing a normalisation is a reviewable change |
| `sampled_size_strings` | **now empty** — same reason |

## Findings this suite produced — and what was done about them

The suite caught **four real nondeterminism bugs**. All four have been **fixed at
the source** rather than normalised away. The history is kept because it is the
evidence that this suite does something.

| # | Script | Bug | Fix |
|---|---|---|---|
| 1 | `data-integrity-check.sh` | `$sample` for type-consistency → counts wobbled (`{"number":87,"string":13}` vs `{"number":85,"string":15}`) | deterministic sampler |
| 2 | `document-bloat-advisor.sh` | `$sample` for `dominant_fields` → sizes wobbled (`title:13B` vs `title:12B`) | deterministic sampler + tie-broken sort |
| 3 | `perf-advisor.sh` | `slow_queries` membership decided by a wall-clock threshold → *which* queries qualified changed with cache warmth | split into `query_timings` (deterministic membership) + `slow_queries` (measurement) |
| 4 | `perf-advisor.sh` | COLLSCAN audit built probe values from `findOne()`, i.e. an **arbitrary** document → a numeric probe of `val/2` scanned a different fraction each run, changing `docs_scanned` and sometimes the chosen plan | probe the first document by `_id` |
| 5 | `perf-advisor.sh` | `index_health[].unused` reads `$indexStats` access counters — which the tool's **own probe queries mutate**, and which the engine updates **asynchronously** | treated as a measurement (allowlisted); `redundant` still asserted |

| 6 | *the harness* | The planner chose **IXSCAN in one run and COLLSCAN in the next** for the same probe, because table statistics were still stale from the bulk seed and background `ANALYZE` landed mid-suite | `kit.seed()` now runs `ANALYZE` after seeding |

Bugs 5 and 6 are the subtle ones: the suite passed in isolation and in most full
runs, but failed about **2 runs in 7** under load. An intermittently-failing
determinism test is worse than none — it trains people to re-run until green.

Bug 6 is worth dwelling on because it was **not a bug in the scripts at all**.
`perf-advisor` was behaving correctly and reporting exactly what the engine told
it; the engine's answer legitimately changed as PostgreSQL's cost estimates
improved. Immediately after a bulk insert the planner is working from stale
statistics, so a probe on a non-leading index column was costed as an index scan
in one run and a sequential scan in another.

The fix belongs in the harness, not the tool: `kit.seed()` now issues `ANALYZE`
so every scenario measures against settled statistics. Verified by running the
full suite **6 consecutive times with no failures**, against 2 failures in 7
before.

The general lesson: when a determinism test flakes, the first question is
whether the *tool* is unstable or whether the *environment it observes* is. Only
the first is a bug to fix in the tool.

Bug 4 is the interesting one: it was **invisible until bug 3 was fixed**. While
the timing noise was being normalised away, it masked a genuine logic defect
underneath. That is the argument for keeping the volatile-field allowlist as
small as possible — every entry can hide a real bug.

### The deterministic sampler

Both samplers now take half the documents from **each end** of `_id` order
instead of `$sample`. Head+tail rather than head-only is deliberate: mixed types
usually arrive from schema drift over time, so the oldest and newest documents
are exactly where the disagreement lives. Sampling only the head would
systematically miss a type change introduced after the collection was created.

Verified after the fix: 3 consecutive runs byte-identical, with the findings
still detected (`invoices.amount {"number":86,"string":14}`;
`dominant_fields "body:4002B,notes:2002B,title:12B"`).

### What remains volatile — and why that is correct

`slow_queries` and the PostgreSQL live counters stay in the allowlist. These are
**measurements, not findings**: whether a query crosses 50 ms genuinely depends
on cache warmth and machine load. The fix was not to force them stable but to
stop *deriving structure* from them — hence `query_timings`, whose membership and
`results` counts are deterministic while only `ms` moves.

## Run

```bash
export DB_PASSWORD='<your-password>'
cd testing && pytest scenarios/determinism
```

Requires a running `documentdb-local` container (see the repo README).
