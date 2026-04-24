# AGENTS.md

This repository is an **Agent Skills** pack for **Azure DocumentDB (with MongoDB compatibility)** — the managed Azure service built on the open-source [DocumentDB](https://github.com/microsoft/documentdb) project. Every skill targets Azure DocumentDB specifically; rules call out DocumentDB features that differ from community MongoDB (`cosmosSearch` vector indexes, `createSearchIndexes` full-text search, cluster M-tiers, Entra RBAC, CMK, etc.).

## How agents should use this kit

1. Read the skill front matter (`skills/*/SKILL.md`) to decide which skill applies to the user's task.
2. Open that skill's `SKILL.md` for full instructions and the list of rule files / references.
3. Open individual rule files or `references/` docs only as needed — don't pre-load the whole repo.

Every skill folder has a `SKILL.md` with YAML front matter containing `name` and `description` (the fields Agent Skills–compatible tools use for discovery). Rule file names are prefixed by category (`model-`, `vector-`, `fts-`, `local-`, etc.) so an agent can match a task to a rule by keyword.

## Skills in this kit

### Best-practice rule collections

These skills each describe a feature area and link to short rule files with incorrect/correct examples.

| Skill | Folder | When to use |
|---|---|---|
| `documentdb-data-modeling` | `skills/data-modeling/` | Designing schemas, embed vs reference, 16 MB limit, denormalization, schema versioning |
| `documentdb-cluster-sharding` | `skills/cluster-sharding/` | Picking an M-tier, scaling decisions, shard-key design at TB scale |
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
- **Picking / sizing a cluster** → `documentdb-cluster-sharding`
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

The same `skills/` tree is consumable by:

- **Claude Code** — copy or symlink `skills/` to `.claude/skills/` (project) or `~/.claude/skills/` (user).
- **GitHub Copilot (CLI / IDE)** — this `AGENTS.md` at the repo root is the entry point; Copilot reads it automatically.
- **Gemini CLI** — symlink `AGENTS.md` to `GEMINI.md`, or copy its contents.
- **Any Agent Skills–compatible tool** — each skill folder has a `SKILL.md` with `name` + `description` front matter, per the [Agent Skills](https://agentskills.io/) format.

See `README.md` for the exact per-tool install commands and the skill-validation script.

