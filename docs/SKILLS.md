# Azure DocumentDB Agent Skills

Capability reference for the skills bundled with [`documentdb-agent-kit`](../README.md).

This kit follows the [Agent Skills](https://agentskills.io/) format. Every skill folder under `skills/` has a `SKILL.md` with `name` + `description` front matter, so Agent Skills–compatible tools (Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot, …) can discover them automatically.

For installation, see [README.md](../README.md).

## Skill types

The kit contains two kinds of skills:

### Rule-folder skills — `<category>/<rule>.md`

Best-practice rules grouped by feature. Each rule follows the same shape:
why it matters → incorrect example → correct example → references.

| Folder | Prefix | Focus |
|---|---|---|
| [`data-modeling/`](../skills/data-modeling/) | `model-` | Embed vs reference, 16 MB limit, denormalization, schema versioning |
| [`sharding/`](../skills/sharding/) | `sharding-` | When to shard vs stay single-shard, shard-key selection (read-heavy vs write-heavy), logical/physical shard mental model, scale-up vs scale-out, hot-partition diagnosis, `sh.shardCollection` / `sh.reshardCollection`, 4 TB logical-shard budget |
| [`query-optimization/`](../skills/query-optimization/) | `query-` | `explain("executionStats")`, avoiding `COLLSCAN` |
| [`indexing/`](../skills/indexing/) | `index-` | Index-type selection (single / compound-ESR / multikey / wildcard / hashed / 2dsphere / TTL), query-pattern → index-shape cookbook, index budget, safe `hideIndex` → `dropIndex` lifecycle |
| [`driver/`](../skills/driver/) | `driver-` | MongoDB driver/SDK usage (singleton client, pooling) |
| [`vector-search/`](../skills/vector-search/) | `vector-` | `cosmosSearch` with DiskANN / HNSW / IVF, PQ, fp16 |
| [`full-text-search/`](../skills/full-text-search/) | `fts-` | `createSearchIndexes` + `$search` for BM25 keyword / phrase / fuzzy; custom analyzers (keyword + edgeGram) for prefix matching on IDs; `pathHierarchy` for hierarchical identifiers; multi-field search indexes; hybrid (BM25 + vector) with RRF |
| [`high-availability/`](../skills/high-availability/) | `ha-` | Enabling HA + zone redundancy, cross-region replica, automatic backup retention, documented SLAs |
| [`storage/`](../skills/storage/) | `storage-` | Premium SSD v2 high-performance storage: compute-tier-gated IOPS/bandwidth caps, v1 vs v2 selection, limitations (no CMK, migration paths), disk-hydration sequencing |
| [`security/`](../skills/security/) | `security-` | TLS, Private Endpoint, Microsoft Entra RBAC, CMK |
| [`monitoring/`](../skills/monitoring/) | `monitoring-` | Slow query logs, metrics & alerts |
| [`local-deployment/`](../skills/local-deployment/) | `local-` | Docker image choice, Compose, TLS, env-driven config, dev/prod parity |

### Standalone SKILL.md skills — `<skill>/SKILL.md`

Single-purpose skills the agent loads when its trigger description matches.

| Skill | Triggers |
|---|---|
| [`mcp-setup/`](../skills/mcp-setup/) | Configuring the DocumentDB MCP server (connection string, transport, shell profile) |
| [`azure-deployment/`](../skills/azure-deployment/) | Provisioning an Azure DocumentDB cluster (`Microsoft.DocumentDB/mongoClusters`) — Bicep (with Key Vault), Azure CLI one-shot, Terraform pointer, firewall, connection string, teardown. See also [`examples/azure-deployment/`](../examples/azure-deployment/) for a no-agent ready-to-run deploy. |
| [`natural-language-querying/`](../skills/natural-language-querying/) | "How do I query…", filter/aggregate/group requests, SQL → MQL translation |
| [`query-optimizer/`](../skills/query-optimizer/) | "Why is this query slow?", index review, `explain()`-driven tuning (indexing deep-dive lives in its `references/`) |
| [`connection/`](../skills/connection/) | Connection pool / timeout / retry tuning; serverless vs OLTP vs OLAP patterns |

## Use when

- Designing document schemas for Azure DocumentDB
- Sizing cluster tiers (M10 – M200+) and deciding when to shard
- Writing or reviewing queries and aggregation pipelines
- Configuring MongoDB drivers against Azure DocumentDB
- Implementing vector search (DiskANN / HNSW / IVF via `cosmosSearch`)
- Applying product quantization or half-precision indexing for AI workloads
- Running DocumentDB locally via Docker / Compose
- Configuring HA, cross-region replication, CMK, firewall, and RBAC
- Optimizing indexes or diagnosing slow queries

## Layout

```
skills/
  <category>/            # rule-folder skill (data-modeling, vector-search, …)
    <rule>.md            # one markdown file per rule
    references/          # deep-dive reference docs (optional)
  <skill>/               # standalone skill (mcp-setup, query-optimizer, …)
    SKILL.md             # agent-facing activation + instructions
    references/          # reference docs the skill loads at runtime
```

## Validating

A PowerShell validator lives at [`../scripts/validate-skills.ps1`](../scripts/validate-skills.ps1). It verifies that every `skills/*/` folder contains a `SKILL.md` with valid YAML front matter containing both `name` and `description`:

```powershell
pwsh ../scripts/validate-skills.ps1
```

Run it after adding new skills or editing front matter.
