# documentdb-agent-kit

[![Status: Public Preview](https://img.shields.io/badge/Status-Public%20Preview-orange?style=flat)](https://azure.microsoft.com/support/legal/preview-supplemental-terms/)

> [!IMPORTANT]
> **Public Preview.** This project is currently in Public Preview. APIs,
> configuration, on-disk layout, skill contents, and installer behavior may
> change in breaking ways before General Availability. There is no SLA.
> Provided "as-is"; see the [Azure Preview Supplemental Terms](https://azure.microsoft.com/support/legal/preview-supplemental-terms/).
> Not recommended for production workloads.

A bundle of agent skills + an MCP server for **Azure DocumentDB (MongoDB-compatible)** — the fully managed Azure service built on the open-source [DocumentDB](https://github.com/documentdb/documentdb) project (Postgres-backed, 99.03% MongoDB-compatible).

Skills follow the [Agent Skills](https://agentskills.io/) format and the kit ships with plugin manifests for Claude Code, Cursor, Codex, Gemini CLI, and GitHub Copilot.

👉 **Capabilities and skill catalog:** [`docs/SKILLS.md`](docs/SKILLS.md)

## Diagnostic Toolbox — Quickstart

Beyond the text skills, the kit ships **deterministic diagnostic scripts** and a
**knowledge-base router** that inspect a *local* DocumentDB container and return
evidence-based answers (reading both the MongoDB API and the PostgreSQL engine
underneath). They need only `docker`, `bash`, and `python3` — no MCP server, no
cloud, no API keys. Full guide: [`docs/DIAGNOSTICS.md`](docs/DIAGNOSTICS.md).

### The tools (`scripts/`)

All are **read-only** (they never modify data) and **cross-layer** (MongoDB API +
PostgreSQL engine). Each takes `--db <name>`; add `--json` for a compact
machine-readable result (what the router consumes).

| Diagnostic | Answers | `--json` |
|--------|---------|:--:|
| `document-bloat-advisor` | Which collections have large text TOASTed and detoasted on every scan; which field to split out. | ✅ |
| `toast-split-advisor` | Which large fields can move to a side collection and the projected hot-document size. | ✅ |
| `index-redundancy-finder` | Redundant (prefix/duplicate/reverse) or unused indexes safe to drop. | ✅ |
| `db-config-advisor` | Working set vs cache, TOAST share, cache-hit ratios — evidence-based config review. | ✅ |
| `perf-advisor` | Overall health: collection-scan audit, query timing, PG I/O / locks / config. | ✅ |
| `data-integrity-check` | Orphaned foreign-key references and mixed-type fields (hard structural integrity). | ✅ |

Common flags: `--container NAME`, `--password PASS`, `--port`, `--pg-port`; env
vars `DB_USER` / `DB_PASSWORD` / `PORT` / `PG_PORT` are also honored. **No password
is baked in** — set `DB_PASSWORD` (or pass `--password`).

### Quickstart

```bash
# 0. start a local DocumentDB container (choose any password; the scripts read it)
docker run -dt --name documentdb-local -p 10260:10260 \
  -e USERNAME=docdbadmin -e PASSWORD=Test1234 \
  ghcr.io/microsoft/documentdb/documentdb-local:latest
export DB_PASSWORD=Test1234          # the scripts require this (or --password)

# 1. seed demo data
bash scenarios/ecommerce/seed.sh           # -> "ecommerce"
bash scenarios/contoso/seed.sh             # -> "contoso" (TOAST demo)

# 2. diagnose (read-only; add --json for machine output)
bash scripts/document-bloat-advisor.sh --db contoso
bash scripts/index-redundancy-finder.sh --db ecommerce

# 3. or ask in natural language — the router picks the tool (no LLM, no container)
bash knowledge-base/kb-route.sh --db contoso "why are my aggregations slow even though I have indexes"
```

The diagnostics also have host-portable Python and PowerShell entry points.
They require Python 3.10+ and Docker Desktop, but do not require Bash or WSL:

```powershell
python scripts\document-bloat-advisor.py --db contoso
.\scripts\index-redundancy-finder.ps1 --db ecommerce --json
```

The Python launcher executes the same read-only diagnostic logic inside the
Linux DocumentDB container, so Linux, macOS, and Windows share one behavior
contract.

Demo datasets are seeders under [`scenarios/`](scenarios/) (they plant the
problems the tools find). The kit is guarded by **two test loops** — deterministic
script tests in [`testing/`](testing/README.md) and cross-model skill evals in
[`evals/`](evals/README.md), plus an MSBench benchmark in
[`benchmarks/`](benchmarks/documentdb-sdk-skills/README.md) — all described in
[`docs/TESTING.md`](docs/TESTING.md).

> **Benchmark platform support:** Run the SDK benchmark natively on an ARM64
> or AMD64 host. Running its AMD64 images on an ARM64 host via emulation is
> **not supported**; use an AMD64 runner to validate the published x86-64
> MSBench images. See the [ARM64 test report](docs/ARM64-BENCHMARK-REPORT.md).

- **Router:** [`knowledge-base/README.md`](knowledge-base/README.md) · **Demo datasets:** [`scenarios/`](scenarios/)
- **Testing:** [`docs/TESTING.md`](docs/TESTING.md) · **Route cost study:** [`benchmarks/documentdb-route-efficiency/`](benchmarks/documentdb-route-efficiency/README.md)
- **DocumentDB compatibility quick-start:** [`compat/`](compat/QUICKSTART.md) — run a MongoDB-compatible Node.js e-commerce project end-to-end on DocumentDB.

## Repo Structure

```
skills/
  <category>/            # rule-folder skill (data-modeling, vector-search, …)
    <rule>.md            # one markdown file per rule
    references/          # deep-dive reference docs (optional)
  <skill>/               # standalone skill (mcp-setup, query-optimizer, …)
    SKILL.md             # agent-facing activation + instructions
    references/          # reference docs the skill loads at runtime
scripts/                 # diagnostic toolbox — read-only analyzers + seeders
knowledge-base/          # NL → script router (kb.json + kb_route.py) + demo
scenarios/contoso/       # ready-to-run TOAST demo dataset (+ optional scaling-benchmark/)
compat/                  # MongoDB-compatible ecommerce project on DocumentDB
testing/                 # Diagnostic Regression Suite — deterministic diagnostics (pytest)
evals/                   # Cross-Model Skill Evaluations — routing, quality, and cost (Vally)
benchmarks/              # MSBench Skill-Efficacy Benchmark + route-cost study
docs/                    # Skills, diagnostics, testing, and installation guidance
```

## Installation

The kit ships with a one-command installer that wires both the **skills** and
the [`microsoft/documentdb-mcp`](https://github.com/microsoft/documentdb-mcp)
server into every detected MCP client. Pick your platform:

| OS | Guide |
|---|---|
| macOS | [`docs/installation/macos.md`](docs/installation/macos.md) |
| Linux | [`docs/installation/linux.md`](docs/installation/linux.md) |
| Windows | [`docs/installation/windows.md`](docs/installation/windows.md) |

### Skills-only (any agent)

To install just the skill catalog into whichever agent you're using — no MCP server — via the [skills.sh](https://skills.sh/) CLI:

```bash
npx skills add Azure/documentdb-agent-kit
```

This drops the rule docs into your agent's skill directory but **does not** install the MCP server. Use one of the per-OS guides above if you want the DB tools too.

> To update later, re-run the same `npx skills add Azure/documentdb-agent-kit` command — it re-fetches the latest `main` and overlays updated rule files. For installer-based updates and per-agent plugin update commands, see [`docs/installation/updating.md`](docs/installation/updating.md).

> 💡 **Accept the optional `find-skills` helper when prompted.** During `npx skills add` the installer will ask whether to install [`find-skills`](https://github.com/skills-sh/find-skills) — say **yes**. It's a tiny meta-skill that lets agents auto-discover the right DocumentDB skill for a task (e.g. *"how do I create a BM25 index?"* → auto-loads `documentdb-full-text-search`) instead of relying on you to invoke skills by name. It's especially useful here because the kit ships 17 skills, more than agents reliably route on their own from `AGENTS.md` alone. If you skipped it, re-run `npx skills add find-skills` to add it later.

For uninstall, troubleshooting, manual install, updating, and per-agent plugin marketplaces, see [`docs/installation/`](docs/installation/README.md).

## Configuration

The MCP server is administrator-controlled: tools never accept runtime connection strings. Set `DOCUMENTDB_CONNECTION_PROFILES` in your shell before launching the agent.

### Microsoft Entra / OIDC (recommended)

```bash
export DOCUMENTDB_CONNECTION_PROFILES='{"sandbox":{"authMode":"entra","endpoint":"<cluster>.mongocluster.cosmos.azure.com","tokenScope":"https://ossrdbms-aad.database.windows.net/.default","allowedHosts":["*.mongocluster.cosmos.azure.com"]}}'

az login --tenant <tenant-id>
```

In Azure hosting, use managed identity or workload identity and grant that identity access to the backend database. The server uses `DefaultAzureCredential`, so the same profile shape works for local Azure CLI login and managed deployments.

### Local / sandbox SCRAM

```bash
export DOCUMENTDB_CONNECTION_PROFILES='{"local":{"uriEnv":"DOCUMENTDB_LOCAL_URI"}}'
export DOCUMENTDB_LOCAL_URI='mongodb://localhost:27017'
```

### Tool capability gates

Read tools are enabled by default. Higher-impact tools are opt-in:

```bash
export ENABLE_WRITE_TOOLS=true        # insert / update / delete / find_and_modify
export ENABLE_MANAGEMENT_TOOLS=true   # drop_database, drop_collection, create_index, ...
```

Or edit [`mcp.json`](mcp.json) directly. See the [DocumentDB MCP Server docs](https://github.com/microsoft/documentdb-mcp) for the full configuration surface.

## Compatibility

Works with Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot, and other Agent Skills–compatible tools.

## License

MIT
