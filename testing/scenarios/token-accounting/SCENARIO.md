# Scenario: token accounting

**Suite:** Diagnostic Regression Suite — guarding a Cross-Model Skill
Evaluations component.
**Infrastructure:** none. No container, no credentials, no network.

## What it guards

`evals/harness/token_usage.py`, which turns the Copilot CLI's local session
store into per-task cost artifacts (tokens, AI credits, cost-to-green) and
aggregates them into the model × arm comparison table.

These numbers are the ones most likely to end up in a GTM claim, so they are
also the ones where a quietly wrong denominator does the most damage. Every test
here pins one specific way the cost story could mislead.

## The four traps being pinned

| Trap | Why it matters | Test |
|---|---|---|
| Counting cached input as spend | `cache_read_tokens` is a **subset** of `input_tokens` (verified: 0 of 6,348 real rows had cache_read > input). Skills are sent once then read from cache, so raw input overstates their marginal cost by ~20× | `test_fresh_input_subtracts_cache_reads` |
| Cost-to-green on a failed run | A run that gives up early is cheap. Letting it report a cost-to-green makes failure look like efficiency | `test_failed_run_reports_no_cost_to_green` |
| Credits-per-pass when nothing passed | Must be **undefined** — not `0` (looks free) and not a crash | `test_credits_per_pass_is_none_when_nothing_passed` |
| A single run presented as a mean | Agent output is non-deterministic; n=1 is not a result | `test_underpowered_cells_are_flagged` |

Two further properties are asserted because they were easy to get wrong:

- **Failed attempts are charged to the successes.** Three runs at 10 credits
  with one pass means a passing result cost **30**, not 10.
- **Subagent spend is reported separately** rather than dropped, so a skill that
  delegates cannot hide its cost.

## Why it lives in `testing/` and not `evals/`

The module belongs to Cross-Model Skill Evaluations (it measures agent cost),
but it is pure stdlib arithmetic over a synthetic SQLite file — perfectly
deterministic. The Diagnostic Regression Suite is where deterministic things
are proven, so that is where its contract lives.

The scenario's `conftest.py` overrides the root `require_container` fixture with
a no-op, which is what makes it infrastructure-free. That is deliberate: it lets
CI run this on every PR without Docker or credentials.

## Verification performed

Beyond "the tests pass", two mutations were injected to confirm the suite can
actually fail:

| Mutation | Caught by |
|---|---|
| `fresh = inp` (stop subtracting cache reads) | 3 tests |
| `credits_per_pass` divided by *runs* instead of *passes* | 1 test |

## Run

```bash
cd testing && pytest scenarios/token-accounting     # no container needed
```
