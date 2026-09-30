# Testing the agent kit

The kit is tested in **three complementary suites**. The first two have
opposite success criteria — conflating them is the main design mistake to avoid
— and the third is the publication layer.

| | **Diagnostic Regression Suite** | **Cross-Model Skill Evaluations** | **MSBench Skill-Efficacy Benchmark** |
|---|---|---|---|
| Subject | diagnostic scripts and router | text skills driving an agent | code produced by an agent |
| Question | "Is the answer stable and repeatable?" | "Is the output good, and what did it cost?" | "Does the produced application satisfy the fixed rubric?" |
| Success | identical canonicalised JSON and exact contracts | beats its control arm over repeated model runs | treatment/control `pass@k` delta |
| Runtime | ~2 min, free | minutes to hours, costs AI credits | slow, Docker/gated platform access |
| Home | [`testing/`](../testing/) | [`evals/`](../evals/) | [`benchmarks/`](../benchmarks/documentdb-sdk-skills/README.md) |
| CI | every PR | dispatch/monthly | PR validation, manual publication |

The Diagnostic Regression Suite and Cross-Model Skill Evaluations support
iteration. The MSBench Skill-Efficacy Benchmark produces the externally
citable result.

A diagnostic script is a **tool**: the same database must give the same answer
every time. An agent is not: it must be measured as a distribution against a
control. Applying either standard to the other produces nonsense.

---

## Prerequisites

For a step-by-step handoff on Apple Silicon or Intel MacBooks, including the
live database fixture and benchmark controls, see
[Testing on a MacBook](TESTING-MACOS.md).

The `static` scenarios in the Diagnostic Regression Suite need **nothing at
all**. Everything else needs a running container.

```bash
# 1. Start DocumentDB Local
docker run -d --name documentdb-local \
  -p 10260:10260 -p 9712:9712 \
  -e USERNAME=docdbadmin -e PASSWORD='<choose-a-password>' \
  ghcr.io/microsoft/documentdb/documentdb-local:latest

# 2. Install mongosh INTO the container — the image does not ship it.
#    Match the container's architecture (not necessarily the host's).
MV=2.3.8
case "$(docker image inspect "$(docker inspect documentdb-local --format '{{.Image}}')" --format '{{.Architecture}}')" in
  amd64) MONGOSH_ARCH=x64 ;;
  arm64) MONGOSH_ARCH=arm64 ;;
  *) echo "Unsupported container architecture" >&2; exit 1 ;;
esac
curl -fsSL "https://downloads.mongodb.com/compass/mongosh-${MV}-linux-${MONGOSH_ARCH}.tgz" -o /tmp/mongosh.tgz
tar xzf /tmp/mongosh.tgz -C /tmp
docker cp "/tmp/mongosh-${MV}-linux-${MONGOSH_ARCH}/bin/mongosh" documentdb-local:/usr/local/bin/mongosh
docker cp "/tmp/mongosh-${MV}-linux-${MONGOSH_ARCH}/bin/mongosh_crypt_v1.so" documentdb-local:/usr/local/lib/
docker exec documentdb-local mongosh --version

# 3. Export the password the container was created with
export DB_PASSWORD='<that-password>'
```

> **Step 2 is not optional.** The `documentdb-local` image ships `psql` but **no
> `mongosh`**, and every diagnostic script talks to the database through
> `docker exec <container> mongosh`. Skipping it makes every scenario fail with
> `executable file not found`, which looks like a broken test rather than a
> missing dependency.

Forgot the password?

```bash
docker inspect documentdb-local \
  --format '{{range .Config.Env}}{{println .}}{{end}}' | grep PASSWORD
```

> **A wrong password reports as `MongoServerError: Invalid key`** — an *auth*
> failure, not a malformed document. The suite now detects this up front and
> aborts once with an actionable message instead of producing ~30 cryptic
> failures.

---

## Diagnostic Regression Suite

```bash
bash testing/run.sh                       # everything (~2 min) -> 86 passed
```

`run.sh` creates `testing-venv/` on first use and passes extra arguments
straight through to pytest.

### No container, no credentials, no network

These run in well under a second and are the first CI job:

```bash
cd testing && pytest scenarios/token-accounting scenarios/evals-config
```

They override the container fixture with a no-op. Use them for a fast check that
the cost metrics and the Cross-Model Skill Evaluations configs are still sane.

### Individual scenarios

```bash
bash testing/run.sh scenarios/determinism           # scripts are reproducible
bash testing/run.sh scenarios/remediation-effect    # the advice actually works
bash testing/run.sh scenarios/kb-router             # routing contract
bash testing/run.sh -m determinism                  # by marker
bash testing/run.sh -k redundancy -v                # by name
```

Markers: `determinism`, `remediation`, `tokens`, `evalsconfig`, `kbrouter`,
`redundancy`, `integrity`, `perf`, `healthy_indexes`, `jsoncontract`.

### What the two headline scenarios prove

**`scenarios/determinism`** runs every script 3× against one untouched database
and asserts the canonicalised `--json` is identical. It found and drove the fix
of **four real nondeterminism bugs** — two `$sample` calls, a latency threshold
that decided list *membership*, and an `explain()` probe built from an arbitrary
`findOne()`. See [its SCENARIO.md](../testing/scenarios/determinism/SCENARIO.md).

**`scenarios/remediation-effect`** is the strongest grading rung available:
rather than asking a model whether the advice is good, it **applies** the advice
and measures the database.

```
tool detects the defect -> fix DERIVED FROM THE TOOL'S OUTPUT -> plan improves
  -> results unchanged -> no new redundancy -> the tool agrees it is fixed
```

The metric is **scan amplification** (`totalDocsExamined / nReturned`): 2000× →
1×. Raw "documents examined" is the wrong metric on this engine — see
[its SCENARIO.md](../testing/scenarios/remediation-effect/SCENARIO.md).

### Reproducing a determinism check by hand

```bash
for i in 1 2 3; do
  bash scripts/data-integrity-check.sh --db test_determinism --json > /tmp/r$i.json
done
diff /tmp/r1.json /tmp/r2.json && diff /tmp/r2.json /tmp/r3.json && echo IDENTICAL
```

Only `--json` is expected to be stable. The human report embeds a wall-clock
banner and measured latencies by design.

---

## Cross-Model Skill Evaluations

Runs on [Vally](https://microsoft.github.io/vally/). **Everything below the
`lint`/`plan` line costs AI credits.**

```bash
cd evals && npm ci
```

The suite has **two** evals: `documentdb-skills/eval.yaml` asks whether the
right skill fires (binary, reproducible), and
`documentdb-quality/quality-eval.yaml` asks whether the guidance is any good
(blinded cross-model judge panel, not reproducible by construction).

### Free — always do these first

```bash
npm run lint:all               # validate both eval specs
npm run experiment:plan        # resolve the 3x2 triggering matrix
npm run experiment:quality:plan # resolve the quality treatment-vs-control matrix
npm run eval:mock              # triggering eval against the mock executor
```

> ⚠️ **The mock executor invokes no skills** (`Skills used 0`). Positive-trigger
> stimuli therefore always fail and anti-trigger stimuli pass **vacuously**. The
> mock validates plumbing, not behaviour — never quote a mock result.

### Paid — real models

Requires `COPILOT_SDK_AUTH_TOKEN`.

```bash
# One cell, to sanity-check cost before committing to the matrix
npx vally experiment run documentdb-skills.experiment.yaml \
  --variant 'model=claude-opus-5,skills=kit'

# The full matrix: 3 models x {kit, control} x 5 runs
npm run experiment

# Guidance QUALITY, treatment vs control, judged by a blinded 3-vendor panel
npm run experiment:quality
```

The quality experiment is 2 arms x 4 stimuli x 3 runs = 24 agent runs, each
graded by 3 judges = 72 judge calls. Run a single cell first.

The matrix is **3 models × 2 arms × 5 runs = 30 trials per stimulus**. Start
with one cell.

### What "treatment" vs "control" means

The intervention is **the kit's skills being installed and discoverable** —
nothing else differs. The control has no skill files, so there is nothing for
the agent to read; the treatment has them on disk but is **never told to use
them**. For cost, that makes the input-token delta the literal price of the kit
being available and used.

### Two rules for reading Cross-Model Skill Evaluations results

1. **Only deltas are publishable.** An absolute pass-rate is uninterpretable —
   "90% passed" means nothing without knowing what a bare agent scores on the
   same stimuli. Every model runs with the kit and with nothing.
2. **The agent is never told to use the skills.** They are made discoverable as
   a user would have them installed, and no prompt mentions them. This measures
   the kit's *organic* effect, not a hinted best case.

### Cost accounting

```bash
python3 evals/harness/token_usage.py sessions --limit 10

python3 evals/harness/token_usage.py report --session <id> \
  --task orders-api --model claude-opus-5 --arm skills --run 1 \
  --outcome-passed 40 --outcome-total 40 --out results/opus-skills-1.json

python3 evals/harness/token_usage.py compare results/*.json
```

```
| Model | Arm | N | Pass rate | Credits (mean±sd) | Turns | Fresh input tok | Cache share | Credits/pass |
|---|---|---|---|---|---|---|---|---|
| claude-opus-5 | control | 3 | 67% | 812.4±31.2 | 9.0±1.0 | 402,118 | 95% | 1218.6 |
| claude-opus-5 | skills  | 3 | 100% | 941.7±18.5 | 6.3±0.6 | 486,930 | 95% | 941.7 |
```

Three things this table is built to stop you getting wrong:

- **Never quote raw input tokens as the cost of a skill.** `cache_read_tokens`
  is a *subset* of `input_tokens`, and ~95% of input is cache reads, so the
  skill payload is amortised. `Fresh input tok` is the honestly-billed number.
- **A failed run reports no cost-to-green**, otherwise giving up early would
  look like efficiency. `Credits/pass` divides by *passes*, not runs — failed
  attempts are part of the price.
- **Cells with n < 3 are flagged ⚠️.** A mean over one non-deterministic agent
  run is an anecdote.

---

## MSBench Skill-Efficacy Benchmark

The publication layer. See
[`benchmarks/documentdb-sdk-skills/README.md`](../benchmarks/documentdb-sdk-skills/README.md).

### Free — runs on every PR

```bash
cd testing && pytest scenarios/benchmark-config scenarios/benchmark-metrics
```

Validates the registration files, the Harbor task layout, that the instruction
contains **no solution hints**, and that the cost metrics agree with the
Cross-Model Skill Evaluation cost module.
No Docker, no MSBench access, no network.

### Local — needs Docker

On macOS, use Docker Desktop and Python 3 with `pip`. Package installation
via `apt-get` takes place inside the benchmark's Ubuntu container, not on
your laptop; the host scripts do not install system packages.

```bash
cd benchmarks/documentdb-sdk-skills
bash build.sh
bash verify-controls.sh
```

The local build selects the Docker host's architecture. On ARM64 it vendors
ARM64 wheels and a checksum-verified ARM64 `mongosh`, and the controls run that
image natively. **AMD64-on-ARM emulation is not supported**; use an AMD64 host
to validate the published x86-64 MSBench image. The MSBench registry and
dataset remain x86-64.

Both controls matter. A grader that cannot be satisfied makes every score
meaningless; a grader that never fails is worthless.

### Gated — needs internal MSBench access

```bash
pip install keyring artifacts-keyring
pip install msbench-cli --index-url=https://pkgs.dev.azure.com/devdiv/_packaging/MicrosoftSweBench/pypi/simple/
az login

# BOTH arms — a treatment score without its control is not a result
msbench-cli run --benchmark documentdb-sdk-skills          --pass_at_k 5 ...
msbench-cli run --benchmark documentdb-sdk-skills-noskills --pass_at_k 5 ...

msbench-cli report --run_id <id> --output report.json   # includes token cost
```

> `pip install msbench` installs an **unrelated** package. The real tool is
> `msbench-cli` from the private feed.

### The effectiveness report

```bash
msbench-cli report --run_id <treatment> --output treatment.json
msbench-cli report --run_id <control>   --output control.json
python3 benchmarks/documentdb-sdk-skills/report.py \
  --treatment treatment.json --control control.json
```

`report.py` refuses to run on a single arm: an absolute pass rate cannot
distinguish an effective kit from an easy task. Current status and the full
provenance of every number are in
[`benchmarks/documentdb-sdk-skills/docs/REPORT.md`](../benchmarks/documentdb-sdk-skills/docs/REPORT.md).

### Cost per task

The verifier writes MSBench `custom_metrics.json` with per-task token usage, so
runs can be compared across tasks:

| Metric | Why |
|---|---|
| `tokens_fresh_input` | input billed at the uncached rate — the honest cost |
| `cache_read_share_pct` | how much the skill payload was amortised |
| `ai_credits` | the money number |
| `credits_to_green` | cost of a **passing** run only |
| `checks_<category>_passed/_total` | which rung an expensive run was failing |
| `tokens_available` | `0` when harvesting failed, so a gap is never read as free |

---

## The grading ladder

Pick the **strongest criterion the scenario allows** — strongest meaning most
reproducible and hardest to satisfy accidentally.

This is about fit, not about avoiding judges. LLM-as-a-judge is a normal grader
and the right tool for qualities that are genuinely matters of degree (is the
explanation clear? is the guidance well-targeted?), which is why Cross-Model Skill Evaluations use one. It just cannot serve a
scenario whose purpose is to prove **repeatability**,
because the same input can score differently across runs. Where an outcome is
measurable in the system, measure it; where it is a judgement, judge it.

| Rung | Criterion | Used by |
|---|---|---|
| 1 | Determinism (identical output) | `scenarios/determinism` |
| 2 | **Before/after measured delta** | `scenarios/remediation-effect` |
| 3 | Structural assertion | `scenarios/*-contract`, `evals-config` |
| 4 | Semantic equivalence | query-generation scenarios |
| 5 | Behavioural (does it run and do the right thing?) | future app-level evals |
| 6 | Contract conformance | `scenarios/json-contract` |
| 7 | LLM-as-a-judge | qualitative dimensions — blinded, cross-model, reported next to an objective score |

Improvement metrics are gameable, so they are **paired with regression guards** —
`remediation-effect` runs `index-redundancy-finder.sh` to make sure "just index
everything" fails, and asserts the result set is unchanged.

---

## CI

| Workflow | Trigger | Cost |
|---|---|---|
| [`diagnostic-regression.yml`](../.github/workflows/diagnostic-regression.yml) | push, PR, dispatch | free |
| [`skill-evaluations.yml`](../.github/workflows/skill-evaluations.yml) | dispatch, monthly | credits |
| [`skill-efficacy-benchmark.yml`](../.github/workflows/skill-efficacy-benchmark.yml) | PR (validate only), dispatch | free / Docker / gated |

The `validate` job in Cross-Model Skill Evaluations (static guards +
`vally lint` + matrix resolution) always runs and is free, so a broken skill
path is caught **before** any credits are spent. That matters:
`vally --dry-run` validates matrix structure but **not** skill paths, and a
treatment arm whose skills fail to load is silently just a second control arm.

Use the `dry_run` input to validate the matrix from CI for free.

---

## Adding a scenario

See [`testing/CREATE-SCENARIO.md`](../testing/CREATE-SCENARIO.md) and the
template at `testing/scenarios/_scenario-template/`.

Two rules learned the hard way:

- **Seed deterministically.** No `Math.random()` in a fixture — use a seeded
  LCG. A test that cannot be reproduced cannot be debugged.
- **Prove the test can fail.** Inject a mutation and confirm it is caught. Every
  scenario here documents the mutations it was verified against; a green suite
  that cannot fail proves nothing.
