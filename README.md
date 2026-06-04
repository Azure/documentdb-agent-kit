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
