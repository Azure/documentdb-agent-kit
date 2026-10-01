# MSBench effectiveness report

**Status as of 2026-08-13 (`5659218`): NO MSBENCH RUN HAS BEEN EXECUTED.**

There is therefore **no effectiveness data yet** — no skills-on vs skills-off
comparison, and no agent token usage. This document records what *has* been
measured, states plainly what has not, and shows how to produce the real report
once a run exists.

> Any number in a GTM deck must come from the generated report described in
> [§4](#4-how-to-produce-the-real-report), not from this page.

---

## 0. What "treatment" and "control" mean here

Borrowed from experimental design: you change **one** thing and hold everything
else fixed, so any difference in the result is attributable to that one thing.

**The treatment is: the DocumentDB agent kit's skills are installed and
discoverable.** That is the entire intervention.

| | Control arm | Treatment arm |
|---|---|---|
| Benchmark | `documentdb-sdk-skills-noskills` | `documentdb-sdk-skills` |
| `~/.copilot/skills/` | **empty** | **17 SKILL.md files** copied in |
| Task, prompt, API contract | identical | identical |
| Model, agent, container, verifier | identical | identical |
| Is the agent told to use the skills? | n/a | **no — never mentioned** |

Implemented in [`shared/ces/runner.sh`](../shared/ces/runner.sh): `SKILLS_ARM=kit`
copies the skills into the agent's personal skills directory; `SKILLS_ARM=control`
installs nothing and deletes the directory defensively, so a stale image layer
cannot leak skills into the control.

### What that means for the TOKEN comparison specifically

The token delta answers: **what does having the kit installed cost?**

- **Control:** there are no skill files, so there is nothing for the agent to
  discover or read. Its input tokens are the task and its own work.
- **Treatment:** the skills are on disk. When the agent judges one relevant it
  *reads* the `SKILL.md`, and those bytes become input tokens.

So `tokens_fresh_input(treatment) − tokens_fresh_input(control)` is, quite
literally, the price of the kit being available and used.

Two things stop that number from being read naively:

1. **Skills are cached.** A payload is sent once and then served from cache
   (~92% of input was cache reads in practice), so raw `tokens_input` badly
   overstates the marginal cost. The report leads with *fresh* (uncached) input.
2. **More tokens per attempt is not the same as more expensive.** "Skills add
   context, therefore skills cost more" is trivially true and uninteresting. The
   question is whether that extra context buys **fewer attempts and more
   successes** — which is why the headline cost figure is *credits per passing
   result*, not credits per run.

The hypothesis being tested is: treatment spends **more per attempt**, needs
**fewer turns**, passes **more often**, and therefore costs **less per success**.
If the run shows otherwise, that is a finding we need, not a result to bury.

### Why not just run it once and look at the number?

Because an absolute score is uninterpretable. If the treatment arm resolves 80%
of attempts, that could mean the kit is excellent — or that the task is easy
enough for any competent agent. Only the control tells you which.
[`report.py`](../report.py) refuses to produce a report from a single arm for
this reason.

---

## 1. What has been measured

The benchmark's **grader** has been validated end-to-end on a local build. This
proves the instrument works. It says nothing about whether the kit helps — no
agent has attempted the task.

Measured on 2026-08-17 at kit commit `3707cb1`. Regenerate at any time — the
script asserts each expected reward and exits non-zero on a deviation:

```bash
bash verify-controls.sh --output "results/$(date -u +%F)-controls-validation.json"
```

| Submission | Reward | Checks |
|---|---|---|
| Oracle (reference implementation) | **1** | 31 / 31 |
| Empty `/app` | **0** | fails at deliverables |
| **Working-but-naive app** | **0** | 20 / 30 — 10 failed |

*(The naive run grades 30 rather than 31 because the ESR ordering check is
skipped when no compound index exists at all — a skipped check is not counted as
a pass or a failure.)*

### Why the naive control is the meaningful one

An empty `/app` failing only proves the harness notices missing files. The naive
app is **fully functional**: correct HTTP behaviour, correct persistence,
duplicate rejection, right result sets. It passes every API and behavioural
check and still scores 0, failing exactly the best-practice checks:

Measured per-category result for that submission:

| Check category | Naive | Oracle | What it covers |
|---|---|---|---|
| `api` | **6/6** | 6/6 | endpoints, status codes, payloads |
| `behavior` | **6/6** | 6/6 | real persistence, round-trip, no duplicates |
| `documentdb` | **0/5** | 6/6 | discriminator, schemaVersion, timestamp, indexing |
| `engine` | **2/4** | 4/4 | query plan, scan amplification |
| `source` | **1/4** | 4/4 | singleton client, pool/timeouts, TLS |
| `skills` | **4/4** | 4/4 | no hardcoded creds, env-driven config |

That is the discrimination the benchmark exists to provide: **basic competence
is perfect (12/12) while best practices collapse (3/13)**. It separates the two
cleanly, which is exactly what a skills benchmark must do.

This is also a useful prior for what the **control arm** may look like. It is a
prior, not a prediction — a real agent is not this app, and may do better or
worse.

### Cost pipeline — proven, but with no agent data

Token harvesting was verified inside the task container by mounting a real
Copilot CLI session store. `custom_metrics.json` was written with
`tokens_available: 1` and populated fields:

```json
{
  "tokens_fresh_input": 148301071,
  "tokens_cache_read":  1618077206,
  "cache_read_share_pct": 91.6,
  "ai_credits": 194081.25,
  "credits_to_green": 194081.25,
  "checks_engine_passed": 4,  "checks_engine_total": 4,
  "reward": 1, "tokens_available": 1
}
```

⚠️ **Those numbers are a plumbing demonstration, not a result.** They are the
usage of an interactive development session that was mounted in to exercise the
code path. The oracle is a `cp` of a reference implementation, not an agent, so
it consumes no tokens of its own. Real figures require an agent run.

One number *is* generalisable and worth carrying into the analysis:
**91.6% of input tokens were cache reads.** Skill payloads are sent once and
then served from cache, which is why the report leads with fresh (uncached)
input rather than raw `tokens_input`.

Reproduce the pipeline (substitute your own session store; the numbers will be
your session's, not these):

```bash
cd benchmarks/documentdb-sdk-skills

# The oracle consumes no tokens of its own, so a real store is mounted in to
# exercise the harvest path end-to-end inside the container.
cp ~/.copilot/session-store.db /tmp/demo-store.db

docker run --rm \
  -v "$PWD/tasks/orders-api-python/tests:/tests:ro" \
  -v "$PWD/tasks/orders-api-python/solution:/solution:ro" \
  -v /tmp/demo-store.db:/root/.copilot/session-store.db:ro \
  documentdb-orders-api-python:latest \
  bash -c '/solution/solve.sh >/dev/null 2>&1 && /tests/test.sh >/dev/null 2>&1; \
           cat /output/custom_metrics.json'
```

Expect `"tokens_available": 1` with populated token fields. Without the mount
you get `"tokens_available": 0` and no token keys at all — which is the correct
behaviour: a missing measurement must never be reported as zero cost.

The same harvester also runs standalone, against any session store:

```bash
python3 shared/verifier/harvest_metrics.py \
  --store ~/.copilot/session-store.db --output-dir /tmp/out
cat /tmp/out/custom_metrics.json
```

---

## 2. What has NOT been measured

| Question | Status |
|---|---|
| Does the kit raise the pass rate? | ⬜ **unknown** — no agent run |
| What does a task cost with vs without the kit? | ⬜ **unknown** |
| Which check categories does the kit move? | ⬜ **unknown** |
| `pass@k` reliability across attempts | ⬜ **unknown** |
| Does it hold across models? | ⬜ out of scope here (that is Cross-Model Skill Evaluations) |

Blocking work, in order:

1. Push both task images to the internal ACR (`harbor-format-curation`).
2. PR `msbench-registration/` into the central repo under
   `benchmarks/skillsbench/`.
3. Run **both** arms with `--pass_at_k 5`.

---

## 3. The report this will produce

Generated by [`report.py`](../report.py). Shape shown here with **illustrative
placeholder values** so reviewers can agree the format before the run:

```
| | Control | Treatment | Delta |
|---|---|---|---|
| Instances       |   5 |   5 |     |
| Resolved        |   1 |   4 |  +3 |
| **Pass rate**   | 20% | 80% | +60% |

| Metric             | Control | Treatment | Delta    |
|--------------------|---------|-----------|----------|
| Fresh input tokens | 403,718 | 488,730   | +85,012  |
| AI credits         |  832.40 |   965.70  |  +133.3  |
| Turns              |     9.8 |      6.6  |    -3.2  |

| Derived                         | Control  | Treatment |
| **Credits per passing result**  | 4,162.00 |  1,207.12 |

| Check category | Control | Treatment | Delta |
| `api`          |    100% |      100% |   +0% |
| `behavior`     |    100% |      100% |   +0% |
| `documentdb`   |     33% |       83% |  +50% |
| `engine`       |     20% |       80% |  +60% |
| `source`       |     60% |       90% |  +30% |
```

**These are placeholders, not findings.** They illustrate the hypothesis the
run will test: the kit costs *more per attempt* but needs *fewer attempts*, so
cost per passing result falls, and the movement concentrates in the
`documentdb` / `engine` / `source` categories while `api` / `behavior` stay flat
in both arms.

If the real run contradicts that — for instance if `api`/`behavior` also move,
suggesting the control arm is simply worse at the basic task — the benchmark
design needs revisiting, not the write-up.

---

## 3b. What "quality" means here — and what the judge is

**There is no LLM judge in this benchmark.** The verifier makes zero model
calls. The judge is **30 deterministic pytest checks**, and the quality
comparison between arms is the per-category pass rate
(`checks_<category>_passed / _total`).

| Module | Checks | What it judges |
|---|---|---|
| `check_api` | 6 | endpoints, status codes, payload shapes |
| `check_behavior` | 6 | real persistence, round-trip, no duplicates |
| `check_documentdb` | 6 | discriminator, schemaVersion, timestamp, indexing, ESR |
| `check_engine` | 4 | query plan, scan amplification, index actually used |
| `check_source` | 4 | singleton client, pool/timeouts, TLS |
| `check_skills` | 4 | no hardcoded credentials, env-driven config |

That is a real quality signal and a reproducible one. But it measures a
specific thing, and the claim must match it.

### What this can and cannot support

✅ **Can support:** *"agents with the kit installed follow Azure DocumentDB
best practices more often"* — that is precisely what the rubric encodes, and
the per-category table shows where.

❌ **Cannot support (without qualification):** *"the kit produces better
solutions."* Three blind spots:

1. **Ties are invisible.** Two submissions both scoring 31/31 may differ a lot
   in readability, structure or error handling. The rubric cannot separate them.
2. **Unanticipated merit scores zero.** The rubric rewards only what it names.
   An agent that solves the problem in a smarter way we did not encode gets no
   credit for it.
3. **The rubric is our opinion, frozen into code.** If a rule is wrong or
   incomplete, the benchmark measures the wrong thing — and does so
   confidently, with a reassuring number attached.

### Where a judge would belong

Not here. The verifier runs offline in a task container with no model access,
and the reward is binary, so a judge would fit badly. Qualitative assessment
belongs in **Cross-Model Skill Evaluations**, which drives real models and has native support for
`panel` / prompt graders.

**Status: built** — [`evals/documentdb-quality/quality-eval.yaml`](../../../evals/documentdb-quality/quality-eval.yaml)
scores guidance quality with a blinded three-vendor judge panel against an
anchored rubric, treatment vs control, with correctness as a hard gate. Not yet
executed against real models.

So the division of labour across the kit is now:

| Claim | Evidence | Where |
|---|---|---|
| "the scripts are reproducible" | byte-identical output | Diagnostic Regression Suite |
| "the right skill fires" | `skill-invocation`, binary | Cross-Model Skill Evaluations, `eval.yaml` |
| **"the guidance is better"** | **blinded judge panel** | **Cross-Model Skill Evaluations, `quality-eval.yaml`** |
| "the produced code follows best practice" | 30 deterministic checks | MSBench Skill-Efficacy Benchmark, this benchmark |

This benchmark still cannot speak to guidance quality — that is not its job, and
the quality eval now covers it.

---

## 4. Reproducing every number

Each stage below is independent — you can stop after any of them. Stages 1–2
need only Docker; stage 3 onward needs internal MSBench access.

### TL;DR — everything that needs no internal access

Copy-paste. Reproduces every number in [§1](#1-what-has-been-measured) from a
clean checkout in about 25 minutes. **Verified by running it end-to-end from a
fresh clone** — 50 config tests, both images built offline, all three controls
behaving as documented.

```bash
git clone https://github.com/Azure/documentdb-agent-kit.git
cd documentdb-agent-kit

# 1. config guards — no Docker, no credentials, ~1s
python3 -m venv testing-venv && testing-venv/bin/pip install -q -r testing/requirements.txt
(cd testing && ../testing-venv/bin/python -m pytest -q \
    scenarios/benchmark-config scenarios/benchmark-metrics)

# 2. build both images offline (wheels resolved on the host)
cd benchmarks/documentdb-sdk-skills
bash build.sh

# 3. the grader validation: oracle=1, empty=0, naive=0
bash verify-controls.sh
```

Everything below is the same thing, stage by stage, with the internal-access
stages included.

### Prerequisites

```bash
# Docker, plus the MSBench CLI for stages 3+
export PATH="$HOME/pgmongo/msbench-tools/venv/bin:$PATH"
msbench-cli version          # -> 0.3.51
az login                     # runs submit under your entitlement
```

> `pip install msbench` fetches an **unrelated** public package. The real tool
> is `msbench-cli` from the internal feed — see `msbench-tools/README.md`.

---

### Stage 1 — Build the images (Docker only, ~10 min)

```bash
cd benchmarks/documentdb-sdk-skills
bash build.sh
```

`build.sh` stages two things before `docker build`, both deliberately:

- **`.skills/`** — the kit's skills, copied from the sibling `skills/` tree so
  the build context stays narrow.
- **`.wheels/`** — every Python dependency, resolved **on the host** and
  installed with `--no-index`. The task promises the agent no internet during
  grading, so the image must not need PyPI to build. (It also cannot: on this
  network `files.pythonhosted.org` is unreachable from Docker's VM even though
  the host can reach it.)

---

### Stage 2 — Reproduce the grader validation (Docker only, ~15 min)

This regenerates every number in [§1](#1-what-has-been-measured):

```bash
bash verify-controls.sh

# or record the outcome as a committed artifact
bash verify-controls.sh --output results/$(date -u +%F)-controls-validation.json
```

Expected output — and the script exits non-zero if any control deviates:

```
control: oracle   REWARD=1   CHECKS=31/31
control: empty    REWARD=0
control: naive    REWARD=0   CHECKS=20/30
    api 6/6   behavior 6/6   documentdb 0/5
    engine 2/4   source 1/4   skills 4/4
```

Run one at a time with `--only naive`. The naive control is the meaningful one;
see [`controls/README.md`](../controls/README.md) for why.

Each run seeds 20,000 filler documents, which is why it is not fast. That
volume is required, not incidental: on a 4-row collection a sequential scan is
genuinely cheaper and the engine checks would fail the oracle itself.

---

### Stage 3 — Run the benchmark locally through MSBench (no ACR push)

The task is registered `task_style: harbor-native`, so `--backend local` runs
the whole thing on your machine — no image push, no central-repo registration.
**Do this before publishing anything.**

```bash
pip install "msbench-cli[harbor]"

msbench-cli run \
  --benchmark documentdb-sdk-skills \
  --dataset msbench-registration/documentdb-sdk-skills/dataset.jsonl \
  --backend local \
  --runner shared/ces/runner.sh
```

The arm is selected by the runner's `SKILLS_ARM` variable (`kit` or `control`).
It **fails loudly** if `SKILLS_ARM=kit` but the skills are absent — a treatment
arm whose skills silently fail to load is just a second control arm, and would
produce a confident, wrong "the kit makes no difference".

---

### Stage 4 — Publish the images and register (internal access)

```bash
# Build and push to the internal registry
harbor-format-curation import orders.toml
harbor-format-curation build --profile staging orders.toml
harbor-format-curation update-database --profile staging orders.toml
```

Then PR both registration folders into the central benchmarks repo:

```
msbench-registration/documentdb-sdk-skills/            -> benchmarks/skillsbench/documentdb-sdk-skills/
msbench-registration/documentdb-sdk-skills-noskills/   -> benchmarks/skillsbench/documentdb-sdk-skills-noskills/
```

Each folder carries `registry.json`, `benchmark_loaders.toml` and
`dataset.jsonl`. **`registry.json` is required** by the live platform; the
Cosmos benchmark's registration predates that requirement and would be rejected
today.

---

### Stage 5 — Run both arms

```bash
for arm in documentdb-sdk-skills documentdb-sdk-skills-noskills; do
  msbench-cli run \
    --benchmark "$arm" \
    --dataset "msbench-registration/$arm/dataset.jsonl" \
    --pass_at_k 5 \
    --runner shared/ces/runner.sh
done
```

**Both arms, always.** A treatment score with no control is not a result — 80%
resolved could mean an excellent kit or an easy task, and nothing in the number
distinguishes them.

`--pass_at_k 5` uses the unbiased estimator `1 − C(n−c,k)/C(n,k)`. Agent runs
are non-deterministic; a single attempt is an anecdote.

---

### Stage 6 — Generate the effectiveness report

Committed results let a number quoted later be traced to the run that produced
it. Write them into `results/` (generated output — the directory may not exist
until you create it):

```bash
DATE=$(date -u +%F)

msbench-cli report --run_id <treatment-run-id> \
  --output "results/$DATE-effectiveness-treatment.json"
msbench-cli report --run_id <control-run-id> \
  --output "results/$DATE-effectiveness-control.json"

python3 report.py \
  --treatment "results/$DATE-effectiveness-treatment.json" \
  --control   "results/$DATE-effectiveness-control.json" \
  --out       "results/$DATE-effectiveness.md"
```

Two rules, both enforced by tests in `testing/scenarios/benchmark-config/`:
**arms must be committed in pairs** (a treatment score with no control is not a
result), and **every result carries provenance** — `run_id`, `image_tag`,
`dataset_version`, `kit_commit`, `model`, `pass_at_k`. Raw MSBench dumps stay
gitignored; only the curated artifact is checked in. The full contract is in
the [benchmark README](../README.md#results).

`report.py` **refuses to run on a single arm**. Add `--json` for machine-readable
output.

The per-instance token metrics travel inside those exports: the verifier writes
`$OUTPUT_DIR/custom_metrics.json` and MSBench surfaces it as
`custom_metrics_values`.

---

### Stage 7 — Guidance quality (Cross-Model Skill Evaluations, not MSBench)

MSBench grades produced code against a fixed rubric. It cannot say whether the
*advice* was good — that lives in Cross-Model Skill Evaluations:

```bash
cd evals && npm ci
npm run experiment:quality:plan   # free: resolve the matrix
npm run experiment:quality        # blinded 3-vendor judge panel, treatment vs control
```

---

### Continuous checks (no infrastructure, every PR)

```bash
cd testing && pytest scenarios/benchmark-config scenarios/benchmark-metrics
```

Validates the registration files, the Harbor layout, that `instruction.md`
leaks no hints, that the verifier parses as Python 3.10 (the image's
interpreter), and that the cost metrics agree with the Cross-Model Skill
Evaluation cost module — all with no
Docker, credentials or network.

---

### What each stage proves

| Stage | Needs | Establishes |
|---|---|---|
| 1–2 | Docker | the grader can pass, can fail, and **discriminates** |
| 3 | Docker + `msbench-cli[harbor]` | the Harbor/MSBench wiring works |
| 4–5 | internal access | a citable `pass@k` for both arms |
| 6 | — | the effectiveness + cost report |
| 7 | Copilot SDK auth | whether the *guidance* is better |
| CI | nothing | the configuration has not rotted |

Stages 1–2 are worth running on every meaningful change to the verifier. They
are the only ones that answer "is this instrument still trustworthy", and they
cost nothing but time.

---

## 5. Reading the numbers honestly

Four traps, each guarded by a test in
`testing/scenarios/benchmark-metrics/`:

**Never quote `tokens_input` as the cost of the kit.** `cache_read_tokens` is a
*subset* of it, and ~92% of input is cache reads. Use `tokens_fresh_input`.

**A pass rate without a control arm means nothing.** `report.py` refuses to run
on one arm for this reason. 80% could be an excellent kit or an easy task.

**Cost per *passing result*, not per run.** Failed attempts are part of the
price of a success, so credits are divided by passes. A treatment arm that costs
more per attempt but passes far more often is cheaper where it counts.

**`tokens_available: 0` means "not measured", never "free".** Instances missing
token data are excluded from cost means and reported separately, so a
harvesting failure cannot quietly drag an average down.

Also: agent runs are non-deterministic. `report.py` flags any arm with fewer
than 3 instances as indicative rather than measured, and `--pass_at_k 5` exists
so a single lucky or unlucky attempt does not become the headline.

---

## 6. Where each number comes from in the code

| Number | Written by | Read by |
|---|---|---|
| `reward` (0/1) | `shared/verifier/runner.sh` → `/logs/verifier/reward.txt` | MSBench (Harbor contract) |
| per-check results | `pytest --ctrf` → `/logs/verifier/ctrf.json` | `harvest_metrics.py` |
| `checks_<category>_*` | `harvest_metrics.py: read_ctrf()` | `report.py` |
| token counts, `ai_credits` | `harvest_metrics.py: read_usage()`, from the Copilot CLI session store | `report.py` |
| observed model, endpoint, reasoning effort, agent and CLI version | `harvest_metrics.py`, losslessly encoded as numeric custom metrics | `report.py`, which rejects missing/mismatched model provenance |
| `custom_metrics.json` | `harvest_metrics.py: main()` → `$OUTPUT_DIR` | `msbench-cli report` |
| `resolved`, `pass_at_k_status` | MSBench | `report.py: summarise()` |
| the tables above | `report.py: render()` | you |

Inspect any layer directly:

```bash
# the metric artifact, from a local run
docker run --rm -v "$PWD/tests:/tests:ro" -v "$PWD/solution:/solution:ro" \
  documentdb-orders-api-python:latest \
  bash -c '/solution/solve.sh >/dev/null && /tests/test.sh >/dev/null 2>&1; \
           cat /output/custom_metrics.json'

# the same code, against your own Copilot session store
python3 benchmarks/documentdb-sdk-skills/shared/verifier/harvest_metrics.py \
  --store ~/.copilot/session-store.db --output-dir /tmp/out && cat /tmp/out/custom_metrics.json

# the Cross-Model Skill Evaluations equivalent (same cost definitions, pinned equal by test)
python3 evals/harness/token_usage.py sessions --limit 10

# the guards on all of the above
cd testing && pytest scenarios/benchmark-metrics scenarios/benchmark-config
```

The two cost implementations (`harvest_metrics.py` for MSBench Skill-Efficacy Benchmark,
`evals/harness/token_usage.py` for Cross-Model Skill Evaluations) cannot share an import — the
harvester must run inside a minimal task container — so
`test_harvester_agrees_with_the_skill_evaluation_cost_module` pins them to identical
output instead. If they ever diverge, that test fails rather than the two
publishing different costs for the same run.
