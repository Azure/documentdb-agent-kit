# DocumentDB Agent-Kit — Knowledge Base Layer

This is the layer that sits **above** the scripts and skills: it turns a
developer's **natural-language question** into the **exact target to use** — a
read-only diagnostic **script** (Route A) or a text **skill** (Route B).

```
                 natural-language query
                          │
                          ▼
                 ┌──────────────────┐
                 │  knowledge base   │   kb.json  (single source of truth)
                 │  + router         │   kb-route.sh
                 └────────┬─────────┘
        Route A (scripts) │ Route B (skills)   + multi-hop workflow (guarded)
        ┌────────────────┴────────────────┐
        ▼                                  ▼
  a diagnostic script                a skill's SKILL.md
  (scripts/*.sh, measured facts)     (skills/*/SKILL.md, guidance)
```

The router scores a question against **both** spaces and reports the best of each
(`match` for scripts, `skill_match` for skills) plus a `recommended` route — so a
"run the TOAST advisor" question lands on a script, while a "how do I read explain
output" question lands on a skill.

Unlike a text-only skill kit (which hands the model prose and hopes it picks the
right approach), this layer gives a **deterministic, explainable routing
decision** and the ready-to-run command — while remaining fully consumable by an
LLM agent for the semantic cases.

## Files

| File | Role |
|------|------|
| `kb.json` | Declarative KB: `tools` (Route A scripts + intents), `skills` (Route B text targets + intents), `routes_one_hop` / `routes_one_hop_skills`, `workflow_schema`, and `workflows` (multi-hop, currently one scaffold). Edit this to extend the kit. |
| `kb-route.sh` | CLI wrapper (bash): arg parsing + presence checks; passes inputs to `kb_route.py` via env vars. |
| `kb_route.py` | Routing engine (stdlib python3, no deps): keyword/example scoring → best script + exact command **and** best skill + `SKILL.md` to open. Standalone so it can be linted/tested/imported. |
| `kb_route_demo.py` | Teaching/debug aid: prints the full scoring walkthrough (per-tool score + signal breakdown) and how the router lands on the winner. `python3 knowledge-base/kb_route_demo.py [query]`. |
| `README.md` | This file. |

## One-hop routing (implemented)

```bash
# route a question to the right script
bash knowledge-base/kb-route.sh "why are my writes slow?"
bash knowledge-base/kb-route.sh --db mydb "audit my indexes for redundancy"

# machine-readable (for the agent / pipelines)
bash knowledge-base/kb-route.sh --json --db mydb "is my cache hit ratio ok?"

# discovery
bash knowledge-base/kb-route.sh --list        # all Route A scripts + example queries
bash knowledge-base/kb-route.sh --skills      # all Route B skills + example queries
bash knowledge-base/kb-route.sh --workflows   # multi-hop workflows (schema/scaffold)
```

Example (Route A — script):

```
Query: "is my cache hit ratio ok, do I need more shared_buffers"
→ Route A (script): [db-config-advisor]  Config & Cache Advisor   (confidence: high, score 9.5)  ← recommended
  matched: cache, cache hit, shared_buffers
  run: bash scripts/db-config-advisor.sh --db mydb [--json]
```

Example (Route B — skill):

```
Query: "how do I read explain output and apply the ESR rule"
→ Route B (skill):  [query-performance-tuning]  Query Performance Tuning Guide   (confidence: high, score 14.4)  ← recommended
  matched: explain, explain output, read explain, esr rule
  open: skills/query-performance-tuning/SKILL.md
```

Currently routed tools (Route A — DocumentDB diagnostics):

| Tool | Answers questions like |
|------|------------------------|
| `index-redundancy-finder` | "why are writes slow", "which indexes can I drop" |
| `document-bloat-advisor` | "aggregations slow despite indexes", "are my documents too big / TOAST" |
| `db-config-advisor` | "cache hit ratio", "do I need more shared_buffers", "working set" |
| `perf-advisor` | "performance checkup", "missing indexes / collection scans" |
| `data-integrity-check` | "orphaned references", "referential integrity", "type consistency" |

Currently routed skills (Route B — text guidance):

| Skill | Answers questions like |
|------|------------------------|
| `query-performance-tuning` | "how do I read explain output", "what is the ESR rule", "find slow queries in prod" |
| `query-optimizer` | "optimize this query", "recommend an index", "verify this query uses an index / check the query plan" |
| `indexing` | "which index type should I use", "design a compound index", "multikey / wildcard / TTL index" |
| `natural-language-querying` | "write a query / aggregation", "translate this SQL to MongoDB" |
| `mcp-setup` | "set up the documentdb mcp server", "configure connection profiles" |
| `azure-deployment` | "provision a cluster with Bicep / Terraform", "get the connection string" |
| `connection` | "tune my connection pool", "maxPoolSize for serverless", "pool exhaustion" |

**Routing is deterministic:** the router scores the query against each target's
`keywords` / `example_queries` in `kb.json`, plus the `routes_one_hop` /
`routes_one_hop_skills` signal, and returns a ranked result **per space** (best
script, best skill) with a confidence,
alternatives, and a `recommended` route. No LLM required; same input → same route.

**Keyword matching differs by space, on purpose:**

- **Tools (Route A / scripts) — 1-gram:** each keyword is split into single
  tokens; every distinct matching query token scores `+1.5`. This favors
  **recall** — a paraphrase like *"scan of the whole collection"* still matches
  the `collection scan` keyword. Harmless, because the scripts are read-only, so
  triggering an extra diagnostic costs nothing.
- **Skills (Route B) — phrase-aware:** a multi-word keyword scores `+3.0` only as
  a full-phrase substring (a single-word keyword `+1.5`). This keeps
  **precision**, because routing to the wrong *guidance* is a real cost.

Both spaces then add `+2.5×` best example-query overlap and `+2.0×` one-hop boost.

Troubleshooting is rarely one script. The KB models a workflow as a **guarded
diagnostic graph** (an AND/OR decision graph — the classic sequential-diagnosis
structure): each **step** runs a tool; each **edge** is conditional on the
observed result; the agent advances until it reaches a conclusion. This directly
supports "run check A; depending on the result, run B or C" with dependencies
between steps.

The structure is defined in `kb.json → workflow_schema`, and one **illustrative
scaffold** (`slow-writes`, marked `status: scaffold`) shows the shape:

```
slow-writes:
  check_redundant_indexes ──(findings>0)──▶ conclude: drop redundant indexes
                          └(findings=0)──▶ check_document_bloat
                                              ├(bloat)──▶ conclude: split large text
                                              └(none)──▶ check_config ──▶ conclude…
```

> Workflows are intentionally **not yet populated/validated** — this layer only
> provides the skeleton so real troubleshooting graphs can be added over time.
> The agent (or a future traversal script) walks the graph, running the tool at
> each node and matching the reported result to an edge.

## Extending the KB

- **Add a one-hop tool (Route A script):** append an entry to `tools[]` in
  `kb.json` with its `script`, `invocation`, `keywords`, and `example_queries`.
  The router picks it up automatically — no code change.
- **Add a one-hop skill (Route B text target):** append an entry to `skills[]`
  in `kb.json` with its `id`, `name`, `title`, `path` (`skills/<folder>/SKILL.md`),
  `keywords`, and `example_queries` — and, optionally, a couple of representative
  queries to `routes_one_hop_skills.examples`. The router scores it automatically.
- **Add a workflow:** append to `workflows[]` following `workflow_schema`
  (`entry`, `steps`, `depends_on`, guarded `yields`).

Routing is regression-guarded by the `kb-router` scenario
(`testing/scenarios/kb-router/`); add a row to its `expected-findings.yaml`
(`routes:` for a script, `skill_routes:` for a skill) when you add a target.

## How the agent should use this layer

1. On a natural-language question, call `kb-route.sh --json "<query>"`.
2. Look at `recommended` (`"script"` or `"skill"`):
   - **script** → if `confident`, run the emitted `match.command` (filling
     `--db`), then interpret the script's measured output for the user.
   - **skill** → if `skill_confident`, open the `skill_match.open` `SKILL.md` and
     answer from its guidance (Route B — no script is run).
3. If a multi-hop workflow applies, start at its `entry` step and follow the
   guarded edges using each step's result.
4. If neither space is confident, fall back to `--list` / `--skills` and ask the
   user to clarify.
