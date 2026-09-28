# documentdb-sdk-skills

A **skill-efficacy benchmark**: does a coding agent obey Azure DocumentDB best
practices when it merely *has* the [documentdb-agent-kit](../../README.md)
skills installed?

> **Status: built and verified locally; not yet submitted to MSBench.** Both
> images build offline, the oracle scores 1, and both an empty and a
> working-but-naive submission score 0. See
> [Verification status](#verification-status).

## The question

Not "is the kit good?" — unfalsifiable. This one:

> Given the same task, the same model and the same environment, does an agent
> **with** the DocumentDB skills installed produce a measurably better service
> than one **without** — and what did each cost?

## Two arms, always

| Benchmark | Skills installed | Role |
|---|---|---|
| `documentdb-sdk-skills` | yes, discoverable, **never mentioned** | treatment |
| `documentdb-sdk-skills-noskills` | none | control |

The control arm is a **separately registered benchmark**, not a runtime flag.
That mirrors the platform's existing `skillsbench` / `skillsbenchnoskills`
convention.

**Only the delta is publishable.** An absolute pass@k on either arm alone
cannot be interpreted — you cannot tell a good kit from an easy task.

## The organic-discovery protocol

`shared/ces/runner.sh` copies the skills into the agent's personal skills
directory as normally discoverable skills, then drives the **default** agent
with **no hint** to use them. `instruction.md` is deliberately silent about
indexing, ESR, connection pooling, schema versioning and type discriminators —
a static test (`testing/scenarios/benchmark-config/`) fails the build if any of
those words appear in it.

Hinting would turn "does an installed kit get applied?" into "can the model
follow an instruction?" — a much easier question with a much less useful answer.

The instruction *does* state the scale requirement ("millions of orders", the
customer lookup is the hot path). That is a requirement, not a hint: without it,
choosing not to index would be a defensible engineering decision rather than a
miss.

## What gets evaluated

| # | Category | Module | Strength |
|---|---|---|---|
| 1 | **Engine behaviour** | `check_engine.py` | ★★★ strongest |
| 2 | **Live behaviour** | `check_behavior.py` | ★★★ |
| 3 | Data shape & indexing | `check_documentdb.py` | ★★ structural |
| 4 | API conformance | `check_api.py` | ★★ |
| 5 | Security hygiene | `check_skills.py` | ★★ |
| 6 | Client configuration | `check_source.py` | ★ static — used only where no runtime signal exists |

### One advantage this benchmark has over its Cosmos ancestor

The Cosmos benchmark notes that client-side properties "a single-node local
emulator **cannot** prove behaviorally" are checked with static source regex
instead — ~520 lines of it. Given their platform that is the right call; a
static check beats no coverage. It is simply easier to satisfy by accident than
a runtime observation is.

DocumentDB lets us avoid the trade-off. It is MongoDB-compatible on the surface
and **PostgreSQL underneath**, and the verifier talks to *both*. So instead of
grepping for `create_index(` and hoping:

- `explain()` through the Mongo API → was the query planned as an index scan,
  and how many documents did it read per document returned?
- `pg_stat_user_indexes` → did the index actually get **used**, or is it dead
  weight costing write throughput?

An agent can fake the source. It cannot fake the engine's own statistics.
Our `check_source.py` is ~130 lines, not 520, because almost everything moved
to a stronger rung.

### Model provenance

The current MSBench command surface used here does not configure a model in the
benchmark invocation. To prevent an undocumented platform model change from
looking like a skill regression or improvement, each instance reads the actual
model identifier from the Copilot CLI session store. The verifier losslessly
encodes the model set, API endpoint, reasoning effort, agent identity, and
observable Copilot CLI version into numeric `custom_metrics.json` fields.

`report.py` refuses to publish a treatment/control comparison if any instance
lacks model provenance, if instances within an arm used inconsistent model
sets, or if the two arms used different model identifiers. If MSBench adds a
supported explicit model option, the workflow should pin it as well as retaining
the observed-value check.

### The metric: scan amplification

`totalDocsExamined / nReturned`.

Raw "documents examined" is the **wrong** metric here — measured on DocumentDB
Local, the planner picks an index scan even for very unselective predicates:

| Query | Plan | Examined | Returned |
|---|---|---|---|
| `amount > 490` (selective) | IXSCAN | 760 | 760 |
| `amount > 10` (unselective) | IXSCAN | 19,960 | 19,960 |

Both are healthy: they read only rows they return. Amplification captures that
independently of selectivity — 2000× before an index, 1× after.

### Grading at realistic volume

The contract seeds only 4 rows through the API, but the engine checks run
against **20,000** filler documents loaded by the verifier
(`bulk_filler` in `conftest.py`), followed by `ANALYZE`.

This is necessary, not a workaround: on a 4-document collection a sequential
scan genuinely *is* cheaper, PostgreSQL is right to choose it, and the oracle
itself would fail. The task tells the agent the service runs against millions
of orders, so the verifier must grade at a size where that statement has
consequences.

## Cost metrics

MSBench's reward is binary — it says whether a submission complied, not what it
cost. The verifier writes `$OUTPUT_DIR/custom_metrics.json` (MSBench's
first-class per-instance hook, surfaced by
`msbench-cli report --output report.json`) with token usage harvested from the
Copilot CLI's own session store:

| Metric | Meaning |
|---|---|
| `tokens_fresh_input` | input **actually billed** at the uncached rate |
| `tokens_input` / `tokens_cache_read` | raw counts, for transparency |
| `cache_read_share_pct` | how much of the payload was amortised by caching |
| `ai_credits` | the money number |
| `agent_turns` / `agent_requests` | round trips |
| `credits_to_green` | cost of a **passing** run (absent when it failed) |
| `checks_<category>_passed/_total` | which rung failed, per category |
| `tokens_available` | `0` when harvesting failed — so a missing value is never read as free |

**Do not quote `tokens_input` as the cost of a skill.** `cache_read_tokens` is a
*subset* of `input_tokens`, and the skill payload is cached after first use — on
a real session, 91% of input was cache reads. `tokens_fresh_input` is the honest
figure.

`credits_to_green` is emitted **only** for a run that passed; otherwise an agent
that gave up early would look like the cheapest one.

## Layout

```
documentdb-sdk-skills/
├── orders.toml                       # harbor-format-curation config
├── msbench-registration/
│   ├── documentdb-sdk-skills/        # treatment: registry.json + loaders + dataset
│   └── documentdb-sdk-skills-noskills/   # control
├── shared/
│   ├── base/Dockerfile               # DocumentDB Local + mongosh + verifier deps
│   ├── base/start-documentdb.sh
│   ├── ces/runner.sh                 # installs skills, un-hinted
│   ├── contracts/orders.json         # the scenario contract
│   └── verifier/
│       ├── conftest.py               # contract loading, both DB clients, filler
│       ├── check_api.py
│       ├── check_behavior.py
│       ├── check_documentdb.py
│       ├── check_engine.py           # ← the differentiator
│       ├── check_source.py
│       ├── check_skills.py
│       ├── harvest_metrics.py        # cost metrics -> custom_metrics.json
│       └── runner.sh                 # reward.txt entrypoint
└── tasks/orders-api-python/
    ├── task.toml  instruction.md
    ├── environment/{Dockerfile,reference/}
    ├── solution/solve.sh             # oracle
    └── tests/{test.sh,checks.py}
```

`registry.json` is **required** by the live platform — the Cosmos benchmark's
registration predates it and would be rejected today.

## Reward model

`tests/test.sh` writes `0` or `1` to `/logs/verifier/reward.txt`. A run scores
`1` only when **every** mandatory check passes. A CTRF report
(`/logs/verifier/ctrf.json`) records per-check results so a failure is
diagnosable without re-running.

### No verification is skipped, deliberately

The platform's own `skillsbench` config carries several
`skip = "oracle", reason = "Non-deterministic: …"` entries. Under a **binary**
reward one flaky check corrupts the entire signal, so `[tasks.skip-verification]`
here is empty and a test enforces that: a check that cannot be made
deterministic must be **removed**, not skipped.

## Reproducing the results

```bash
bash build.sh              # build both images (offline, from vendored wheels)
bash verify-controls.sh    # oracle=1, empty=0, naive=0 — asserts all three
```

Full stage-by-stage guide, from a Docker-only build through to a published
`pass@k`, in [`docs/REPORT.md` §4](docs/REPORT.md).

## Building and running locally

```bash
cd benchmarks/documentdb-sdk-skills
bash build.sh
bash verify-controls.sh
```

The build and verification entrypoints pin containers to `linux/amd64` because
the benchmark's vendored Python wheels and checksum-verified `mongosh` archive
are x86-64. Docker Desktop uses amd64 emulation automatically on Apple Silicon.

`--backend local` lets MSBench run harbor-native benchmarks entirely on your
machine, so the whole benchmark can be iterated **without** pushing to the
internal registry:

```bash
pip install "msbench-cli[harbor]"
msbench-cli run --benchmark documentdb-sdk-skills \
  --dataset msbench-registration/documentdb-sdk-skills/dataset.jsonl \
  --backend local
```

## Results

`results/` is **generated output**, not source. It may be absent — a fresh
clone has none, and pruning stale artifacts is housekeeping. The benchmark's
configuration is valid either way; the tests only assert things about results
that actually exist.

When results *are* committed, two rules apply (enforced by
`testing/scenarios/benchmark-config/`):

| Rule | Why |
|---|---|
| **Arms come in pairs** — a `*-treatment.json` needs its `*-control.json` | a treatment score with no control is not a result: 80% resolved could mean an excellent kit or an easy task |
| **Provenance is mandatory** — `run_id`, `date`, `benchmark`, `image_tag`, `dataset_version`, `kit_commit`, `model`, `pass_at_k` | without `kit_commit` you cannot say which skills the agent had; without `model` you cannot compare like-for-like |

Naming: `<date>-<what>[-<arm>].{json,md}` — a `.json` for tooling, a `.md` for
humans. Raw MSBench dumps stay gitignored; only curated artifacts are committed.

Regenerate the grader-validation artifact any time:

```bash
bash verify-controls.sh --output "results/$(date -u +%F)-controls-validation.json"
```

**No MSBench run has been executed yet**, so there is no effectiveness data.
[`docs/REPORT.md`](docs/REPORT.md) records what has been measured (grader
validation), what has not, and how to generate the real report with
[`report.py`](report.py) once both arms have run.

## Verification status

Verified by running, not by inspection:

| Claim | Status |
|---|---|
| Registration matches the live platform schema | ✅ read from the central repo; asserted by tests |
| Task follows the Harbor layout | ✅ asserted by tests |
| Instruction contains no hints | ✅ asserted (mutation-verified) |
| Cost metrics agree with the Cross-Model Skill Evaluations module | ✅ asserted (mutation-verified) |
| Verifier parses as Python 3.10 (the image's interpreter) | ✅ asserted in CI |
| Images build | ✅ base + task, offline from vendored wheels |
| **Oracle scores 1** | ✅ **REWARD=1, 31 checks passed** |
| **Empty submission scores 0** | ✅ **REWARD=0** |
| **A working-but-naive app scores 0** | ✅ **REWARD=0, 10 checks failed** |
| Cost metrics emitted | ✅ `custom_metrics.json` with per-category counts |
| Submitted to MSBench | ⬜ not yet |

### The discrimination that matters

An empty `/app` failing is a weak result — it proves only that the harness
notices missing files. The real test is a submission that **works**: correct
HTTP behaviour, correct persistence, no DocumentDB best practices.

That app passes **every** API and behavioural check and still scores 0, failing
exactly the ten skill-specific ones:

```
check_documentdb  type discriminator, schemaVersion, queryable timestamp,
                  secondary index exists, queried field is indexed
check_engine      query is not a full scan, scan amplification is low
check_source      connection options set explicitly, TLS not hardcoded off,
                  client is not constructed per request
```

That is the benchmark working as intended: it measures best practices, not
basic competence.

### Three real bugs the controls found

None of these would have been caught by inspection, and all three would have
produced a *wrong published number*:

| Bug | Consequence | Now guarded by |
|---|---|---|
| `check_source.py` regex had catastrophic backtracking (nested quantifiers over lines) | verifier **hung for minutes** on a 6 KB file; replaced with `ast` (~1000× faster) | a CI test banning quantified-group-followed-by-quantifier |
| Credential check matched an f-string **template** (`mongodb://{quote_plus(user)}:{quote_plus(password)}@…`) | **failed the reference implementation** — a false positive would fail every correct submission | a CI test asserting env-driven URIs pass and real secrets still fail |
| Singleton check only looked inside route handlers | the naive app hid its per-request client in a helper and **passed** | a CI test with the exact helper pattern |

The third was found by the naive-submission control, which is precisely what
negative controls are for.

## What is *not* here

- **The skills themselves.** They live in [`skills/`](../../skills/). This
  benchmark measures obedience to them; it does not own them.
- **The fast development loops.** `testing/` (deterministic) and `evals/`
  (cross-model) are for iteration; see [`docs/TESTING.md`](../../docs/TESTING.md).
  This is the slow, hermetic publication layer.
