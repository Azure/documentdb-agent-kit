# Skill review rubric

The grading sheet. The deterministic checks (`check-skill.py`) cover the mechanical items. This file covers the judgment calls — what the script cannot decide.

Use this rubric only after `check-skill.py` has run and you have its JSON. Do not duplicate its work.

---

## Section A — Description quality (Level 1)

The single highest-leverage check. The frontmatter `description` is loaded every turn and used by the agent to *route*. A vague description routes the wrong way every turn for the lifetime of the skill.

Grade against three questions:

1. **Triggers.** Does it list at least 2–3 concrete situations the user might be in? ("Use when designing a new schema, migrating from SQL, deciding between embedding and referencing…") A description that says only *what* the skill is, not *when* to invoke it, fails this check.
2. **Differentiation.** Could the description plausibly match another skill in the same kit? If `documentdb-indexing` and `documentdb-query-optimizer` could trade descriptions and nothing would change, both descriptions are too generic.
3. **Length.** Anthropic's hard limit is 1024 characters. Practical sweet spot is 200–500 characters: long enough to list real triggers, short enough that the routing model reads it cleanly. < 80 chars is almost always too vague. > 800 chars usually means the body leaked into the description.

| Grade | Rule |
|---|---|
| PASS | Lists ≥ 2 concrete trigger situations *and* would not be confused with a sibling skill *and* is 150–800 chars. |
| WARN | One of those three fails. |
| FAIL | Two or more fail, or the description is missing entirely. |

---

## Section B — Architecture cost (Levels 2 + 3)

What does this skill cost the user *per invocation*? Grade against **token cost from `check-skill.py`**, not line count. Lines are a proxy; tokens are what the runtime actually spends.

The script reports four numbers per skill — quote them verbatim:

| Field | Meaning | Where it shows up |
|---|---|---|
| `level1_always_loaded_tokens` | Frontmatter loaded every turn the kit is installed | The pinboard. ~100 tok per skill is Anthropic's baseline. |
| `level2_on_invocation_tokens` | SKILL.md body, loaded when the skill triggers | The article's "20% vs 7%" measurement. |
| `level3_references_tokens_total` | Sum of all references | Only paid if the body links them in. |
| `pct_of_context_on_invocation` | L1+L2 as a percentage of the context window | The grade. |

Architecture grade (matches the script's `grade.architecture_cost`):

| `level2_on_invocation_tokens` | Grade | Reasoning |
|---|---|---|
| ≤ 5,000 | **PASS** | Within Anthropic's recommended 500-line / ~5k-token ceiling. Article's exemplar was ~1,800 tok (180 lines). |
| 5,001 – 10,000 | **WARN** | Approaching the ceiling. Look for sections that load on different tasks and should be references. |
| 10,001+ | **FAIL** | Antipattern #2. The 20% case from the article. |

Per-reference grading (Level 3):

| Per-file tokens | Grade | Reasoning |
|---|---|---|
| ≤ 4,000 | PASS | Loads cleanly when the spine asks for it. |
| 4,001 – 8,000 | OK | Acceptable if the topic genuinely needs the depth. |
| 8,001+ | WARN | Would dominate context if loaded. Split into smaller topic files the spine can pick from. |

Then look at the references:

- **Are they referenced from `SKILL.md`?** A reference file that no `[link](file.md)` points to is an orphan — either the spine should link it, or it should be deleted.
- **Are they independently readable?** Open the largest reference. If it starts mid-context with no recap of *what task it is part of*, the reader landing on it via search will be confused. References should have a 1-sentence "this rule applies when…" preamble.

---

## Section C — Portability (Antipattern #3)

Skim shell-command and code blocks in `SKILL.md` and the largest reference. Flag:

- Absolute paths to a specific machine (`/Users/<name>/...`, `/home/<name>/...`, `C:\Users\<name>\...`).
- Repo-specific module names without a "find this in *your* repo" preamble (`modules/web`, `apps/api`).
- Hardcoded ports, hostnames, or cluster names that are not explicitly examples.

A skill that runs only on the author's machine is not a skill — it is a private note that crashes for the next reader.

---

## Section D — Gotchas (Antipattern #4)

Operational skills *must* have a Gotchas-equivalent section somewhere in the skill (the spine or any reference). "Operational" = the skill produces side effects: deploys, connects, configures, runs, installs.

Look for headings matching: `Gotchas`, `Pitfalls`, `Common mistakes`, `Watch out for`, `Known issues`, `Caveats`, or a "⚠️" / "Note:" pattern that calls out non-default behavior.

Pure-reference skills (concept explainers, decision frameworks) get a pass — there is no environment to be wrong about.

| Skill kind | Gotchas required? |
|---|---|
| Deployment, provisioning, setup, install | Yes — Blocker if absent |
| Connection / driver / runtime config | Yes — Improvement if absent |
| Query / index / schema design | Soft — only if there are known query-engine quirks |
| Pure decision framework / glossary | No |

---

## Section E — Evals (Antipattern #5)

Look for any of: `evals/`, `tests/`, `golden-set/`, `eval.md`, `eval.json`, `eval.yaml`, or a documented "test prompt" set in the spine.

This is a *soft* check. Most useful skills ship without evals and the kit-wide convention may be no evals (note this in your report rather than flagging every skill). Escalate only when the skill encodes:

- Author voice or organizational style.
- Formatting or output-shape contracts that downstream tools depend on.
- Behavior that has changed between model versions (the "model upgrade is not free" failure mode).

For data-modeling, indexing, security, and similar *technical* skills in this kit, missing evals is normal and should be noted once at the kit level, not per-skill.

---

## Section F — Kit-specific gotchas

This kit (`documentdb-agent-kit`) has conventions that differ from the article's defaults. Consult before flagging.

1. **Short spines pointing to siblings is the *target* shape, not a defect.** A 13-line `SKILL.md` linking to four `model-*.md` files passes Section B with the highest mark. Do not score it down for being short.
2. **Reference files are unprefixed plain markdown.** No frontmatter is correct (Antipattern #1's *correct* shape). The convention is `# title` followed by `## Why it matters / ## Incorrect / ## Correct / ## References`.
3. **Cross-skill references exist by design.** `query-optimizer` and `natural-language-querying` load rules from sibling skills. A `[link](../indexing/idx-esr-rule.md)` is legitimate, not an orphan.
4. **Both `validate-skills.ps1` and `check-skill.py` should pass.** They check different things — frontmatter shape vs architecture/antipatterns. Recommend running both in CI; do not recommend merging them.

---

## Output discipline

A skill review report should be ≤ 40 lines for a typical skill. If you find yourself writing more than three findings per category, you are reviewing a different problem (kit-wide audit, refactor proposal) — name it as such and propose a separate session.
