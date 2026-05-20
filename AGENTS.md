# AGENTS.md

This repository is an **Agent Skills** pack for **Azure DocumentDB (with MongoDB compatibility)** — the managed Azure service built on the open-source [DocumentDB](https://github.com/microsoft/documentdb) project. Every skill targets Azure DocumentDB specifically; rules call out DocumentDB features that differ from community MongoDB (`cosmosSearch` vector indexes, `createSearchIndexes` full-text search, cluster M-tiers, Entra RBAC, CMK, etc.).

## How agents should use this kit

### Skill routing (do this first)

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
| `documentdb-query-optimization` | `skills/query-optimization/` | Writing queries that use indexes; reading `explain("executionStats")` |
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
| `documentdb-mcp-setup` | `skills/mcp-setup/` | User has the DocumentDB MCP server installed but hasn't configured `DOCUMENTDB_URI` / transport / shell profile |
| `documentdb-azure-deployment` | `skills/azure-deployment/` | Provisioning an Azure DocumentDB cluster (`Microsoft.DocumentDB/mongoClusters`) via Bicep, Azure CLI, Terraform, or portal; firewall rules; connection string retrieval |
| `documentdb-natural-language-querying` | `skills/natural-language-querying/` | "How do I query…", "filter / group / aggregate…", SQL → MQL translation (read-only queries only) |
| `documentdb-query-optimizer` | `skills/query-optimizer/` | "Why is this slow?", index review, `explain()`-driven tuning; loads `references/core-indexing-principles.md` |
| `documentdb-connection` | `skills/connection/` | Pool-size / timeout / retry tuning for serverless, OLTP, OLAP, or bursty workloads |

## Routing hints for agents

- **Writing / generating a query** → `documentdb-natural-language-querying`
- **"Why is this query slow / how do I index this?"** → `documentdb-query-optimizer`
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

