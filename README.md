# documentdb-agent-kit
\
A collection of skills for AI coding agents working with **Azure DocumentDB (with MongoDB compatibility)** — the fully managed Azure service built on the open-source [DocumentDB](https://github.com/documentdb/documentdb) project (Postgres-backed, 99.03% MongoDB-compatible). Skills are packaged instructions and rule sets that extend agent capabilities.

Skills follow the [Agent Skills](https://agentskills.io/) format.

## Available Skills

The kit contains two kinds of skills under `skills/`:

### Rule-folder skills — `<category>/<rule>.md`

Best-practice rules grouped by feature. Each rule follows the same shape:
why it matters → incorrect example → correct example → references.

| Folder | Prefix | Focus |
|---|---|---|
| `skills/data-modeling/` | `model-` | Embed vs reference, 16 MB limit, denormalization, schema versioning |
| `skills/cluster-sharding/` | `cluster-` | M-tier selection, vertical-first scaling, shard-key design |
| `skills/query-optimization/` | `query-` | `explain("executionStats")`, avoiding `COLLSCAN` |
| `skills/indexing/` | `index-` | Index-type selection (single / compound-ESR / multikey / wildcard / hashed / 2dsphere / TTL), query-pattern → index-shape cookbook, index budget, safe `hideIndex` → `dropIndex` lifecycle |
| `skills/driver/` | `driver-` | MongoDB driver/SDK usage (singleton client, pooling) |
| `skills/vector-search/` | `vector-` | `cosmosSearch` with DiskANN / HNSW / IVF, PQ, fp16 |
| `skills/full-text-search/` | `fts-` | `createSearchIndexes` + `$search` for BM25 keyword / phrase / fuzzy; custom analyzers (keyword + edgeGram) for prefix matching on IDs; `pathHierarchy` for hierarchical identifiers; multi-field search indexes; hybrid (BM25 + vector) with RRF |
| `skills/high-availability/` | `ha-` | Enabling HA, cross-region replica, documented SLAs |
| `skills/security/` | `security-` | TLS, Private Endpoint, Microsoft Entra RBAC, CMK |
| `skills/monitoring/` | `monitoring-` | Slow query logs, metrics & alerts |
| `skills/local-deployment/` | `local-` | Docker image choice, Compose, TLS, env-driven config, dev/prod parity |

### Standalone SKILL.md skills — `<skill>/SKILL.md`

Single-purpose skills the agent loads when its trigger description matches.

| Skill | Triggers |
|---|---|
| `skills/mcp-setup/` | Configuring the DocumentDB MCP server (connection string, transport, shell profile) |
| `skills/azure-deployment/` | Provisioning an Azure DocumentDB cluster (`Microsoft.DocumentDB/mongoClusters`) — Bicep (with Key Vault), Azure CLI one-shot, Terraform pointer, firewall, connection string, teardown. See also [`examples/azure-deployment/`](examples/azure-deployment/) for a no-agent ready-to-run deploy. |
| `skills/natural-language-querying/` | "How do I query…", filter/aggregate/group requests, SQL → MQL translation |
| `skills/query-optimizer/` | "Why is this query slow?", index review, `explain()`-driven tuning (indexing deep-dive lives in its `references/`) |
| `skills/connection/` | Connection pool / timeout / retry tuning; serverless vs OLTP vs OLAP patterns |

**Use when:**
- Designing document schemas for Azure DocumentDB
- Sizing cluster tiers (M10 – M200+) and deciding when to shard
- Writing or reviewing queries and aggregation pipelines
- Configuring MongoDB drivers against Azure DocumentDB
- Implementing vector search (DiskANN / HNSW / IVF via `cosmosSearch`)
- Applying product quantization or half-precision indexing for AI workloads
- Running DocumentDB locally via Docker / Compose
- Configuring HA, cross-region replication, CMK, firewall, and RBAC
- Optimizing indexes or diagnosing slow queries

## Installation

```bash
npx skills add <org>/documentdb-agent-kit
```

## Repo Structure

```
skills/
  <category>/            # rule-folder skill (data-modeling, vector-search, …)
    <rule>.md            # one markdown file per rule
    references/          # deep-dive reference docs (optional)
  <skill>/               # standalone skill (mcp-setup, query-optimizer, …)
    SKILL.md             # agent-facing activation + instructions
    references/          # reference docs the skill loads at runtime
```

## Installation

This kit follows the [Agent Skills](https://agentskills.io/) format. Every skill folder under `skills/` has a `SKILL.md` with `name` + `description` front matter, so Agent Skills–compatible tools can discover them automatically.

### Claude Code

Project-scoped (only this repo sees the skills):

```bash
mkdir -p .claude && ln -s "$(pwd)/skills" .claude/skills
```

User-scoped (every project sees the skills):

```bash
mkdir -p ~/.claude/skills
for d in skills/*/; do ln -s "$(pwd)/$d" ~/.claude/skills/; done
```

On Windows/PowerShell, use `New-Item -ItemType SymbolicLink` or just copy the folder.

### GitHub Copilot (CLI and IDE)

`AGENTS.md` at the repo root is the entry point — Copilot reads it automatically when you open the repo. No extra wiring required. If you want Copilot to see the kit in a *different* repo, copy `AGENTS.md` and the `skills/` folder into that repo's root.

### Gemini CLI

Gemini CLI reads `GEMINI.md`:

```bash
ln -s AGENTS.md GEMINI.md      # or: cp AGENTS.md GEMINI.md
```

### Other Agent Skills–compatible tools

Point the tool at `skills/` as your skills directory. Each `skills/<name>/SKILL.md` is a discoverable skill with its own `name` and `description`.

## Validating skills

A PowerShell validator lives at `scripts/validate-skills.ps1`. It verifies that every `skills/*/` folder contains a `SKILL.md` with valid YAML front matter containing both `name` and `description`:

```powershell
pwsh ./scripts/validate-skills.ps1
```

Run it after adding new skills or editing front matter.

## Compatibility

Works with Claude Code, GitHub Copilot, Gemini CLI, and other Agent Skills-compatible tools.

## License

MIT
