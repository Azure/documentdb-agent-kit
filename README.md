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

The kit ships with a one-command installer that wires both the **skills** and
the [`microsoft/documentdb-mcp`](https://github.com/microsoft/documentdb-mcp)
server into every detected MCP client.

### One-liner (recommended)

**macOS / Linux:**

```bash
curl -fsSL https://raw.githubusercontent.com/Azure/documentdb-agent-kit/main/install.sh | bash -s -- --uri "<your-connection-string>"
```

**Windows (PowerShell):**

```powershell
$env:DOCUMENTDB_URI = "<your-connection-string>"
irm https://raw.githubusercontent.com/Azure/documentdb-agent-kit/main/install.ps1 | iex
```

Local-dev quickstart (no Azure cluster needed, assuming a running documentdb-local container):

```bash
curl -fsSL https://raw.githubusercontent.com/Azure/documentdb-agent-kit/main/install.sh | bash -s -- --uri "mongodb://localhost:27017"
```

### What gets installed

| Path | What |
|---|---|
| `~/.documentdb-agent-kit/agent-kit/` | Clone of this repo (skills + AGENTS.md) |
| `~/.documentdb-agent-kit/mcp-server/` | Clone + build of `microsoft/documentdb-mcp` |

Then, per detected client:

| Client | MCP entry → | Skills → |
|---|---|---|
| Claude Code | `~/.claude.json` | `~/.claude/skills/` (symlinks) |
| Claude Desktop | `claude_desktop_config.json` (per-OS path) | `Claude/skills/` (symlinks, if dir exists) |
| Cursor | `~/.cursor/mcp.json` | — (use Cursor Rules per-project) |
| GitHub Copilot CLI | `~/.copilot/mcp-config.json` | — (copy `AGENTS.md` per-project) |
| Gemini CLI | `~/.gemini/settings.json` | — (use `GEMINI.md` per-project) |

Existing entries in each client's config are preserved — the installer only
adds (or updates) a single `DocumentDB` entry. A timestamped `.bak` backup is
written before every JSON edit.

### Requirements

- `git`
- Node.js 20+ and `npm` (the MCP server is a Node app, built from source on
  install). `--skills-only` mode skips Node requirements.

### Common flags

```text
--uri <conn>        DocumentDB / MongoDB connection string
--yes               Non-interactive (don't prompt)
--dry-run           Print planned changes; write nothing
--uninstall         Remove MCP entries, skill symlinks, and ~/.documentdb-agent-kit
--clients <list>    Comma-separated: claude-code,claude-desktop,cursor,copilot-cli,gemini-cli
--skills-only       Skip MCP server install
--mcp-only          Skip skill linking
--mcp-ref <ref>     Git ref of microsoft/documentdb-mcp (default: main)
--profile <name>    CONNECTION_PROFILES key name (default: default)
```

Connection string can also be supplied via `$DOCUMENTDB_URI` (or
`$env:DOCUMENTDB_URI` on PowerShell). When neither flag nor env var is set and
a TTY is attached, the installer prompts.

### Verify it worked

1. Fully **quit** and reopen each configured client (not just close the window).
2. Ask the agent: *"list databases using the DocumentDB MCP server with connection_profile 'default'"*.
3. You should get back the database list.

### Uninstall

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/Azure/documentdb-agent-kit/main/install.sh | bash -s -- --uninstall --yes
```

```powershell
# Windows
irm https://raw.githubusercontent.com/Azure/documentdb-agent-kit/main/install.ps1 | iex -ArgumentList '-Uninstall','-Yes'
```

Removes the kit's `DocumentDB` MCP entry from every client, removes skill
symlinks, and deletes `~/.documentdb-agent-kit/`. Other MCP servers and your
non-kit skills are left untouched.

### Manual install (no script)

If you don't want to run the installer, every step is documented in the
[`documentdb-mcp-setup` skill](skills/mcp-setup/SKILL.md) (per-client config
file paths, MCP server config template, `CONNECTION_PROFILES` JSON, etc.).
For skills-only manual install:

```bash
# Claude Code (project-scoped)
mkdir -p .claude && ln -s "$(pwd)/skills" .claude/skills

# Claude Code (user-scoped)
mkdir -p ~/.claude/skills && for d in skills/*/; do ln -s "$(pwd)/$d" ~/.claude/skills/; done

# Gemini CLI (project-scoped)
ln -s AGENTS.md GEMINI.md

# GitHub Copilot / other AGENTS.md-aware clients: drop AGENTS.md + skills/ at repo root
```

On Windows, use `New-Item -ItemType SymbolicLink` or copy folders.

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
