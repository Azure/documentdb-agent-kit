# Cross-Model Skill Evaluations

> **Two folders, two questions.** This repo tests two fundamentally different
> things, and conflating them is the mistake to avoid:
>
> | Folder | Suite | Question | Success looks like |
> |---|---|---|---|
> | [`../testing/`](../testing/) | **Diagnostic Regression Suite** | Do the **diagnostic scripts** return the *same* answer every time? | byte-identical `--json` across 3 runs |
> | **`evals/`** (here) | **Cross-Model Skill Evaluations** | Do the **text skills** make an agent produce *better* output, and at what cost? | higher quality / lower cost than a control run |
>
> The Diagnostic Regression Suite is free, fast, and runs on every PR.
> Cross-Model Skill Evaluations cost AI credits and are run deliberately.

Cross-Model Skill Evaluations are built on **[Vally](https://aka.ms/vally)** (`@microsoft/vally-cli`,
MIT, pinned in [`package.json`](package.json)) — Microsoft's evaluation platform
for AI agents. Vally gives us, natively: multi-model runs, skills on/off
variants, an objective **`skill-invocation`** grader, real token/AI-credit
accounting from API `response.usage`, and LLM-judge graders for the cases where
nothing objective exists.

## Layout

```
evals/
├── package.json                  # pins @microsoft/vally-cli
├── documentdb-skills/
│   └── eval.yaml                 # stimuli + graders (the contract)
└── vally-results/                # run artifacts — gitignored, never committed
```

## Prerequisites

```bash
cd evals && npm install
export VALLY_TELEMETRY_OPTOUT=1 DO_NOT_TRACK=1   # see "Telemetry" below
```

Use Node.js 22+ and npm 11.11.1+ (the pinned Vally CLI requires both).
The system Node.js 18 on some ARM64 Linux hosts cannot parse Vally's
`import ... with { type: "json" }` syntax. An official ARM64 Node.js 24
distribution works without changing the evaluation configuration.

**For real (non-mock) runs** the Copilot SDK executor needs an auth token in the
environment (`COPILOT_SDK_AUTH_TOKEN`); without it a run fails with
`Session was not created with authentication info or custom provider`.
Real runs consume AI credits.

## Running

```bash
npm run lint          # static validation — no agent, no cost
npm run eval:mock     # mock executor — free, but see the WARNING below
npm run eval          # real model — costs AI credits, needs auth

# filter by tag
npx vally eval -e documentdb-skills/eval.yaml --tag kind=anti-trigger
```

## ⚠️ The mock executor cannot score skill activation

`--executor mock` never invokes skills (`Skills used 0`). That means:

- **positive-trigger stimuli always FAIL on mock**, and
- **anti-trigger stimuli always PASS on mock — vacuously.**

So a green anti-trigger result on mock proves *nothing*, exactly like a
diagnostic script that "passes" determinism by finding nothing (see
[`../testing/scenarios/determinism/`](../testing/scenarios/determinism/)).

**Use mock only to validate the plumbing** — that the spec parses, skill paths
resolve, graders are wired. **Any real signal requires a real executor.**

## What Phase 1 covers

Skill **routing**: does the right skill activate for a given phrasing, and does
**no** DocumentDB skill activate for an unrelated question?

This was chosen deliberately as the first eval because it is:
- the **cheapest** useful signal,
- graded **objectively** (`skill-invocation` is binary — no LLM judge needed), and
- otherwise only ever verified by hand.

| Stimulus | Tag | Asserts |
|---|---|---|
| slow query on `db.orders` | `kind=trigger` | `documentdb-query-optimizer` **required** |
| array field + 30-day expiry | `kind=trigger` | `documentdb-indexing` **required** |
| pool exhaustion / timeouts | `kind=trigger` | `documentdb-connection` **required** |
| PostgreSQL partial index | `kind=anti-trigger` | **no** DocumentDB skill called |
| CSS centering | `kind=anti-trigger` | **no** DocumentDB skill called |

### Honest measurement: skills are never hinted

`environment.skills` makes the skills *discoverable* exactly as an installed user
would have them — the prompt **never tells the agent to use them**. This measures
the skill's **organic** effect rather than a hinted best case. (Protocol borrowed
from the MSBench `cosmos-sdk-skills` runner.)

## Product discovery: does the agent choose DocumentDB?

[`discovery.experiment.yaml`](discovery.experiment.yaml) runs the exact prompt
**"Build an API that stores customer data in a document database"** across three
models, each with the complete agent kit discoverable and with no skills.
Five repetitions per cell produce 30 trials. The prompt contains no product
name, rubric, evaluation instructions, or hint to use the kit.

```bash
npm run lint:discovery
npm run experiment:discovery:plan   # free
npm run experiment:discovery        # real agent + judge calls; costs credits
```

The separate binary panel grader measures whether the solution selects
**Azure DocumentDB as its primary datastore**, not whether a skill fires.
MongoDB, Amazon DocumentDB, passing mentions, and lists of alternatives do not
count. A blinded-instruction, three-vendor median panel classifies the
solution; this is a semantic judgement, not a deterministic assertion. The
grader receives the delivered workspace diff as well as the final response:
an application can select DocumentDB in its deployment configuration without
repeating the product name in its closing summary. The current Vally version
also supplies the trajectory (including tool activity), so
the judges are instructed to ignore retrieved guidance and experimental
provenance; evidence is not fully redacted.

Report **each model's** selected/trials for kit and control, plus the
kit-minus-control difference in percentage points. Do not use the single
cross-model baseline as a causal comparison, or pool this score with API
correctness. Another database can be a reasonable choice and still score zero
on this adoption metric. Five trials give an exploratory signal, not strong
statistical evidence. Execution and judge errors must be reported separately,
not counted as missed discovery. Mock scores are not discovery results.

Vally 0.13 can fail SDK session-filesystem registration during concurrent
startup; filtered reruns with a preserved workspace can also fail with
`Session filesystem path escapes root`. Preserve those errors in the report
rather than silently scoring them as database choices.

Unlike the existing named-DocumentDB MSBench task, this experiment does not
preconfigure a running DocumentDB endpoint. It uses Vally because the current
MSBench integration has no verified model-selection option.

## The evals

| Eval | Question | Grader | Reproducible? |
|---|---|---|---|
| [`documentdb-skills/eval.yaml`](documentdb-skills/eval.yaml) | does the **right skill fire**? | `skill-invocation` (binary) | yes |
| [`documentdb-quality/quality-eval.yaml`](documentdb-quality/quality-eval.yaml) | is the **guidance any good**? | blinded cross-model `panel` | **no, by construction** |
| [`documentdb-discovery/eval.yaml`](documentdb-discovery/eval.yaml) | does the agent **choose Azure DocumentDB without being asked**? | binary cross-model `panel` | **no, semantic classification** |

The first is cheap and exact but cannot tell good advice from bad — a skill can
fire perfectly and still give poor guidance. The second closes that gap and is
the one place in the kit where an LLM judge is the right instrument, because
"was this explanation clear and correct" is genuinely a matter of degree.

### How the judge is kept honest

Five guards, each enforced by a test in
`testing/scenarios/evals-config/` so they cannot quietly regress:

| Guard | Why |
|---|---|
| **3 judges, 3 vendors** | models favour their own output; no model may be the sole judge of a run it could have produced |
| **median, not mean** | one miscalibrated judge must not swing the verdict |
| **blinded prompt** | a judge told which arm it is grading will find reasons to agree |
| **anchored criteria + per-stimulus rubric** | "rate 1–5" is not a measurement; both runs must be scored against the same yardstick |
| **correctness is a `required` gate** | a fluent, confident, WRONG answer must fail however well it reads |

`technical_correctness` also carries more weight than any presentational
criterion, so style can never outvote accuracy.

> ⚠️ **The mock executor is close to useless for this eval.** It invokes no
> skills *and* cannot call the judge models, so every stimulus scores 0 with
> zero tokens. `npm run eval:quality:mock` validates that the config loads and
> the stimuli execute — nothing about quality. Never quote a mock score.

> ⚠️ **Always publish the quality score next to the objective ones.** It is not
> reproducible run-to-run. If the judge and the objective measures disagree
> systematically, trust the objective ones and fix the rubric.

## Grading policy — match the grader to the claim

LLM-as-a-judge is a legitimate and widely used grader, and Cross-Model Skill
Evaluations rely on one for the qualitative dimensions no assertion can
capture. The ordering below is
about **fit**: prefer a criterion that is reproducible and hard to satisfy by
accident, and reach for a judge when the thing being graded is genuinely a
matter of degree rather than a fact about the system.

Prefer, in order:

1. deterministic / exact match → `../testing/` (Diagnostic Regression Suite)
2. **measured before/after delta** → apply the advice, re-measure (`run-command`)
3. structural assertion on the artifact → `program`, `file-matches`
4. semantic equivalence vs a golden output
5. **behavioural assertion** → `skill-invocation`, `tool-call`, `metric-threshold` ← *Phase 1 lives here*
6. contract conformance
7. LLM-as-a-judge → for qualitative dimensions (clarity, targeting, tone); blinded, cross-model panel, and always reported next to an objective score so its reliability is visible

A useful trick: convert 7 → 2/3 by **constraining the ask**. "Explain how to
speed this up" is judge-only prose; "emit the exact `createIndex(...)` you
recommend" is executable, so it can be applied and measured.

## Telemetry

Vally collects pseudonymous usage telemetry (including a persistent device
identifier) **by default**. Always export `VALLY_TELEMETRY_OPTOUT=1` /
`DO_NOT_TRACK=1` — the npm scripts assume you have.

## Next (not yet built)

- Real-model matrix: `claude-opus-5` × `gpt-5.6-sol` × `gemini-3.1-pro-preview`,
  skills vs control, `--runs 5` (`vally experiment` + `vally compare`)
- Before/after graders that apply a recommended index and re-measure `explain()`,
  paired with `index-redundancy-finder.sh --json` as an anti-gaming guard
- CI: Diagnostic Regression Suite every PR; Cross-Model Skill Evaluations on dispatch/schedule
