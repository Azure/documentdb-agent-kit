# Diagnostic Regression Suite

> **This is the Diagnostic Regression Suite — the deterministic half.** The kit tests two different
> things: `testing/` (here) proves the **diagnostic scripts** return the *same*
> answer every time, while [`../evals/`](../evals/) measures whether the **text
> skills** make an agent produce *better* output, and at what token cost.
> The Diagnostic Regression Suite is free and runs on every PR;
> Cross-Model Skill Evaluations cost AI credits.
> See [`scenarios/determinism/`](scenarios/determinism/) for the repeatability
> contract.

This framework guards the agent-kit's **diagnostic skills/scripts** against
regression. It is modelled on the [Cosmos DB agent-kit `testing-v2`] framework
but adapted for a *diagnostic inspector* rather than an app generator.

Where the Cosmos framework is **contract-first** ("define an API contract, have
an agent build an app, validate the app against the contract"), this framework
is **fixture-first**:

> Seed a database with **known planted problems**, run an agent-kit diagnostic
> script against the live DocumentDB container, and assert the script's findings
> match a fixed `expected-findings.yaml` contract.

Because the diagnostic scripts emit deterministic output (JSON or stable text
markers), the contracts are exact — this is a stronger regression signal than
testing free-form LLM output.

```
seed fixture (known issues)  ──►  run kit script  ──►  assert vs contract
   fixture.js                  scripts/*.py or *.sh     expected-findings.yaml
```

## Layout

```
testing/
  conftest.py              # CLI options (--container, --keep-db) + global fixtures
  pytest.ini              # discovery + markers
  requirements.txt
  run.sh                  # convenience: venv + install + run
  harness/
    kit.py                # run_script(), seed(), drop_db(), container checks
    conftest_base.py      # make_seeded_db_fixture() factory
  scenarios/
    _scenario-template/   # copy this to start a new scenario
    ecommerce-redundant-indexes/   # index-redundancy-finder.sh  (JSON contract)
    ecommerce-data-integrity/      # data-integrity-check.sh     (text markers)
    ecommerce-missing-index/       # perf-advisor.sh             (COLLSCAN audit)
    ecommerce-healthy-indexes/     # false-positive guard (well-indexed DB -> 0 findings)
    json-contract/                 # --json shape/validity guard (all 5 scripts)
```

Each scenario directory contains:

| File | Purpose |
|------|---------|
| `SCENARIO.md` | Fixed description of what is planted and what must be detected |
| `fixture.js` | Deterministic seed that plants the known issues |
| `expected-findings.yaml` | The "answer key" contract |
| `conftest.py` | Builds the scenario's `seeded_db` fixture (one line) |
| `tests/test_*.py` | Asserts the kit script's findings match the contract |

## Prerequisites

- A running DocumentDB local container (default name `documentdb-local`,
  gateway port `10260`, PG port `9712`). Override via env:
  `DOCDB_CONTAINER`, `DOCDB_PORT`, `DOCDB_PG_PORT`, `DOCDB_USER`, `DOCDB_PASSWORD`.
- Python 3.10+, Docker CLI on PATH.

## Run

```bash
# one-shot (creates a venv, installs deps, runs everything)
bash testing/run.sh

# or manually
python3 -m venv testing-venv
testing-venv/bin/pip install -r testing/requirements.txt
cd testing && ../testing-venv/bin/python -m pytest

# a single scenario
cd testing && ../testing-venv/bin/python -m pytest scenarios/ecommerce-redundant-indexes -v

# point at a different container, and keep the seeded DB for inspection
cd testing && ../testing-venv/bin/python -m pytest --container my-docdb --keep-db
```

On Windows, use Python or the matching PowerShell launcher:

```powershell
python scripts\perf-advisor.py --db ecommerce --json
.\scripts\perf-advisor.ps1 --db ecommerce --json
```

The portable launcher requires Python 3.10+ and Docker Desktop, but does not
require Git Bash or WSL. It executes the existing diagnostic logic inside the
Linux DocumentDB container. The Diagnostic Regression Suite uses these Python
launchers on every platform.

If the container isn't running, the whole suite **skips** (it does not fail).

## The regression loop (for skill/script changes)

1. Edit a skill rule or a diagnostic under `scripts/` (`.sh`, `.py`, or `.ps1`).
2. Run `pytest`. Green = behavior preserved.
3. A red test means the change altered detection behavior. Either:
   - it's a **bug** → fix the script, or
   - it's an **intended** behavior change → update the scenario's
     `expected-findings.yaml` *deliberately* (the answer key is the record of
     intended behavior).

This makes every change to the answer key an explicit, reviewable decision.

## Adding a scenario

See [`CREATE-SCENARIO.md`](CREATE-SCENARIO.md). In short: copy
`scenarios/_scenario-template/`, write a `fixture.js` that plants known issues,
encode the answer key in `expected-findings.yaml`, and assert it in
`tests/`.

## Multi-model (agent) layer — optional, complementary

This framework deterministically tests the **scripts** that skills invoke. To
also regression-test how a *frontier-model agent* uses the skills (does it pick
the right tool and read the findings correctly?), layer a prompt-matrix eval
(e.g. promptfoo with `providers:` across OpenAI/Anthropic/Google, or Inspect AI
for sandboxed tool use) on top. The deterministic script layer here is the
foundation; the model layer is additive.

[Cosmos DB agent-kit `testing-v2`]: https://github.com/AzureCosmosDB/cosmosdb-agent-kit/tree/main/testing-v2
