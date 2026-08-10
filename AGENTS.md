# AGENTS.md

This repository is an **Agent Skills** pack for **Azure DocumentDB (with MongoDB compatibility)** — the managed Azure service built on the open-source [DocumentDB](https://github.com/microsoft/documentdb) project. Every skill targets Azure DocumentDB specifically; rules call out DocumentDB features that differ from community MongoDB (`cosmosSearch` vector indexes, `createSearchIndexes` full-text search, cluster M-tiers, Entra RBAC, CMK, etc.).

> **Status: Public Preview.** This kit and its upstream MCP server are
> pre-GA; rule contents, skill shapes, installer behavior, and the MCP
> tool surface may change in breaking ways. No SLA. See the
> [Azure Preview Supplemental Terms](https://azure.microsoft.com/support/legal/preview-supplemental-terms/).
> When acting on the kit, agents should call out this status to the user
> if they're about to commit kit-installed configs into anything that
> looks production-shaped.

## How agents should use this kit

This kit has **two routes**. Decide the route *first*, from what the user said:

| The user says… | Route | What the agent does |
|---|---|---|
| **"use toolbox"** (explicit), or clearly asks to *run the diagnostic scripts* against a live database | **Route A — Diagnostic toolbox** | Use the knowledge-base router to pick and run a **read-only** diagnostic script against the user's *local* DocumentDB container, then report the findings. |
| **anything else** (the default) | **Route B — Text skills** | Route to the best `skills/*/SKILL.md` and answer from guidance. |

**Default to Route B.** Only take Route A when the user **explicitly** says *"use toolbox"* (or unambiguously asks to run the diagnostic scripts / inspect a live local database). Do not run any script on Route B.

### Route A — Diagnostic toolbox (only when the user says "use toolbox")

Deterministic, **read-only** scripts that inspect a *local* DocumentDB container (both the MongoDB API and the PostgreSQL engine underneath) and emit findings. They never modify data; no cloud, no API keys. Steps:

1. **Prerequisites:** a running container (default name `documentdb-local`) and a password exported as `DB_PASSWORD` (or passed via `--password`); `db-config-advisor` is PG-only and needs no password. See [`docs/DIAGNOSTICS.md`](docs/DIAGNOSTICS.md) for the one-line `docker run` and seeding.
2. **Route the question to the exact script** with the knowledge-base router — deterministic keyword scoring, needs no LLM and no container:
   ```bash
   bash knowledge-base/kb-route.sh --db <db> "<the user's question>"
   ```
   It prints the matching tool and the exact command (append `--json` for machine-readable output). See [`knowledge-base/README.md`](knowledge-base/README.md).
3. **Run the recommended command** (all scripts are read-only) and interpret the findings/insights for the user. Present the fix as a recommendation — applying it (e.g. a schema split or dropping an index) is the user's decision.
4. **If the router is not confident** (no match / low score), fall back to Route B.

Tools available on this route: `document-bloat-advisor`, `index-redundancy-finder`, `db-config-advisor`, `perf-advisor`, `data-integrity-check` — catalog in [`README.md`](README.md#the-tools-scripts). Regression-guarded by [`testing/`](testing/README.md).

### Route B — Text skills (default): skill routing (do this first)

This kit ships **17+ skills**, which is too many to reliably pick from a flat table. Agents should route in this order:

1. **Prefer the `find-skills` helper if installed.** Check for `~/.agents/skills/find-skills/` (or the equivalent symlinked location for the current agent). If present, call `find-skills` with the user's task to get the right DocumentDB skill, then open that skill's `SKILL.md`. **Do not** scan the table below in this case.
2. **If `find-skills` is not installed, ask the user once whether to install it** before falling back. Suggest the install command (`npx skills add find-skills`) and explain it is a one-time, ~zero-cost helper that improves routing across this kit's 17+ skills. Wait for an answer.
3. **If the user declines (or the environment cannot install it),** fall back to the manual routing flow:
   - Read the skill front matter (`skills/*/SKILL.md`) and the **Skills in this kit** table below to decide which skill applies.
   - Open that skill's `SKILL.md` for full instructions and the list of rule files / references.
   - Open individual rule files or `references/` docs only as needed — don't pre-load the whole repo.

Every skill folder has a `SKILL.md` with YAML front matter containing `name` and `description` (the fields Agent Skills–compatible tools use for discovery). Rule file names are prefixed by category (`model-`, `vector-`, `fts-`, `local-`, etc.) so an agent can match a task to a rule by keyword.

## Skills in this kit

### Best-practice rule collections

These skills each describe a feature area and link to short rule files with incorrect/correct examples.

| Skill | Folder | When to use |
|---|---|---|
| `documentdb-data-modeling` | `skills/data-modeling/` | Designing schemas, embed vs reference, 16 MB limit, denormalization, schema versioning |
| `documentdb-indexing` | `skills/indexing/` | Choosing the right index type (single / compound / multikey / wildcard / hashed / 2dsphere / TTL); ESR ordering; query-pattern → index-shape cookbook; safe index lifecycle (`hideIndex` → `dropIndex`) |
| `documentdb-driver` | `skills/driver/` | Singleton `MongoClient`, connection reuse fundamentals |
| `documentdb-vector-search` | `skills/vector-search/` | `cosmosSearch` with DiskANN / HNSW / IVF, PQ, fp16, cosine normalization |
| `documentdb-full-text-search` | `skills/full-text-search/` | `$search` with `createSearchIndexes`, custom analyzers (edgeGram, pathHierarchy), fuzzy / phrase / prefix, multi-field indexes, BM25 + vector hybrid |
| `documentdb-high-availability` | `skills/high-availability/` | HA, cross-region replica, 99.99% / 99.995% SLAs |
| `documentdb-security` | `skills/security/` | TLS, Private Endpoint, Entra RBAC, CMK |
| `documentdb-monitoring` | `skills/monitoring/` | Diagnostic settings, slow-query logs, metrics & alerts |
| `documentdb-local-deployment` | `skills/local-deployment/` | Docker image choice, Compose, TLS, env-driven config, dev/prod parity |

### Interactive / workflow skills

These skills walk the user (or another agent) through a task end-to-end.

| Skill | Folder | When to use |
|---|---|---|
| `documentdb-mcp-setup` | `skills/mcp-setup/` | Installing / configuring the DocumentDB MCP server in an agentic client (Claude Code, Claude Desktop, Cursor, Copilot CLI, Gemini CLI, VS Code); defining `CONNECTION_PROFILES` |
| `documentdb-azure-deployment` | `skills/azure-deployment/` | Provisioning an Azure DocumentDB cluster (`Microsoft.DocumentDB/mongoClusters`) via Bicep, Azure CLI, Terraform, or portal; firewall rules; connection string retrieval |
| `documentdb-natural-language-querying` | `skills/natural-language-querying/` | "How do I query…", "filter / group / aggregate…", SQL → MQL translation (read-only queries only) |
| `documentdb-query-optimizer` | `skills/query-optimizer/` | "Why is this slow?", index review, `explain()`-driven tuning; loads `references/core-indexing-principles.md` |
| `documentdb-query-performance-tuning` | `skills/query-performance-tuning/` | End-to-end tuning methodology: reading DocumentDB's Postgres-backed `explain("executionStats")`, the ESR rule, index-backed sorts, covered queries, finding slow queries via Log Analytics `VCoreMongoRequests`; loads `references/documentdb-explain-output.md` |
| `documentdb-connection` | `skills/connection/` | Pool-size / timeout / retry tuning for serverless, OLTP, OLAP, or bursty workloads |

## Routing hints for agents

These map a task to the best **Route B (text) skill**. (On **Route A** — when the
user said *"use toolbox"* — route the same task through `knowledge-base/kb-route.sh`
to a diagnostic script instead.) `kb-route.sh` can also deterministically surface
the best-matching **skill** for these Route-B tasks (`--skills`, or the
`skill_match` / `recommended` fields in `--json` output) if you want a scored pick
rather than reading the table below.

- **Writing / generating a query** → `documentdb-natural-language-querying`
- **"Why is this query slow / how do I index this?"** → `documentdb-query-optimizer`
- **"How do I read explain output / what is the ESR rule / how do I tune query performance / find slow queries in prod"** → `documentdb-query-performance-tuning`
- **"Which index type should I use / design this index"** → `documentdb-indexing`
- **Designing a schema / data model** → `documentdb-data-modeling`
- **Adding vector search to a RAG app** → `documentdb-vector-search`
- **Adding keyword / BM25 search** → `documentdb-full-text-search`
- **Configuring `MongoClient` / connection string** → `documentdb-connection` (pool tuning) or `documentdb-driver` (basic patterns)
- **Setting up the DocumentDB MCP server** → `documentdb-mcp-setup`
- **Provisioning / deploying an Azure DocumentDB cluster (Bicep / CLI / Terraform)** → `documentdb-azure-deployment`
- **Running DocumentDB locally** → `documentdb-local-deployment`
- **HA / DR / SLA questions** → `documentdb-high-availability`
- **TLS / RBAC / encryption / networking** → `documentdb-security`
- **Observability / alerts / slow queries log** → `documentdb-monitoring`

## Cross-tool compatibility

This kit is distributed as an installable plugin/extension for every major coding agent. The plugin bundles the [DocumentDB MCP server](https://github.com/microsoft/documentdb-mcp) (`documentdb-mcp-server` on npm) together with the `skills/` tree.

| Agent | Install command | Update command | Manifest |
|---|---|---|---|
| Skills only (any agent) | `npx skills add Azure/documentdb-agent-kit` | re-run `npx skills add Azure/documentdb-agent-kit` (preferred) or `npx skills update` | walks `skills/` directly (no MCP server) |

> ⚠️ Per-agent plugin install paths are not yet published — see the commented-out rows below for the planned commands.

<!--
| Claude Code | `/plugin marketplace add Azure/documentdb-agent-kit` then `/plugin install documentdb` | `/plugin update documentdb@azure-documentdb` | [`.claude-plugin/`](.claude-plugin/) |
| Cursor | `/add-plugin azure/documentdb-agent-kit` | re-run `/add-plugin azure/documentdb-agent-kit` | [`.cursor-plugin/`](.cursor-plugin/) |
| Codex | `codex plugin marketplace add azure/documentdb-agent-kit` | `codex plugin update documentdb` | [`.codex-plugin/`](.codex-plugin/) + [`.agents/plugins/marketplace.json`](.agents/plugins/marketplace.json) |
| Gemini CLI | `gemini extensions install https://github.com/Azure/documentdb-agent-kit` | `gemini extensions update documentdb-agent-kit` | [`gemini-extension.json`](gemini-extension.json) + [`GEMINI.md`](GEMINI.md) |
| GitHub Copilot CLI | `/plugin install https://github.com/Azure/documentdb-agent-kit.git` | `/plugin update https://github.com/Azure/documentdb-agent-kit.git` | this `AGENTS.md` + [`mcp.json`](mcp.json) |
-->

All paths share the same `skills/` tree. Claude / Cursor / Codex / Copilot also share the root [`mcp.json`](mcp.json); Gemini inlines the same MCP config in its own manifest.

Skills are snapshotted at install time and do **not** auto-update — re-run the relevant update command above to pull new skills or fixes from `main`. The bundled MCP server runs via `npx -y documentdb-mcp-server` and refreshes on every agent restart (subject to npm cache).

See [`README.md`](README.md) for the full per-tool install + configuration walkthrough and [`docs/SKILLS.md`](docs/SKILLS.md) for the capability catalog.

