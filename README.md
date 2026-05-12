# documentdb-agent-kit

A bundle of agent skills + an MCP server for **Azure DocumentDB (MongoDB-compatible)** — the fully managed Azure service built on the open-source [DocumentDB](https://github.com/documentdb/documentdb) project (Postgres-backed, 99.03% MongoDB-compatible).

Skills follow the [Agent Skills](https://agentskills.io/) format and the kit ships with plugin manifests for Claude Code, Cursor, Codex, Gemini CLI, and GitHub Copilot.

👉 **Capabilities and skill catalog:** [`docs/SKILLS.md`](docs/SKILLS.md)

## Installation

The plugin bundles the [DocumentDB MCP server](https://github.com/microsoft/documentdb-mcp) (`documentdb-mcp-server` on npm — Node.js 20+) together with all skills under `skills/`.

### Claude Code

Inside a Claude Code session:

```text
/plugin marketplace add Azure/documentdb-agent-kit
/plugin install documentdb@azure-documentdb
```

### Cursor

```text
/add-plugin azure/documentdb-agent-kit
```

### Codex

```bash
codex plugin marketplace add azure/documentdb-agent-kit
codex plugin install documentdb
```

### Gemini CLI

```bash
gemini extensions install https://github.com/Azure/documentdb-agent-kit
```

### GitHub Copilot CLI

```bash
/plugin install https://github.com/Azure/documentdb-agent-kit.git
```

Then restart Copilot CLI to activate the MCP server. For Copilot in the IDE, [`AGENTS.md`](AGENTS.md) at the repo root is read automatically — no extra wiring.

### Universal one-liner — skills only (no MCP server)

To install just the skill catalog into whichever agent you're using, via the [skills.sh](https://skills.sh/) CLI:

```bash
npx skills add Azure/documentdb-agent-kit
```

This drops the rule docs into your agent's skill directory but **does not** install the MCP server. Use one of the per-agent plugin commands above if you want the DB tools too.

## Updating the kit

New skills, rule fixes, and MCP-server updates are released on `main`. Installs do **not** auto-update — each install path has its own refresh command. Run these when you want to pull in new features or fixes:

| Install path | Update command |
|---|---|
| Claude Code | `/plugin update documentdb@azure-documentdb` |
| Cursor | re-run `/add-plugin azure/documentdb-agent-kit` |
| Codex | `codex plugin update documentdb` |
| Gemini CLI | `gemini extensions update documentdb-agent-kit` |
| GitHub Copilot CLI | `/plugin update https://github.com/Azure/documentdb-agent-kit.git` (or uninstall + reinstall) |
| Skills only (skills.sh CLI) | re-run `npx skills add Azure/documentdb-agent-kit` |

> **Skills CLI note:** `npx skills update` exists but is unreliable for GitHub-sourced skills on the current `skills` CLI release. **Re-running `npx skills add Azure/documentdb-agent-kit` is the recommended refresh path** — it re-fetches the latest `main` and overlays the updated rule files. Add `--all` if you originally installed with `--all`.

The MCP server is fetched via `npx -y documentdb-mcp-server` each time the agent launches the server, so MCP-server updates land automatically on the next agent restart (subject to npm cache). Skill files are snapshotted at install time and only refresh when you run one of the commands above.

To see what's changed between releases, check [`CHANGELOG.md`](CHANGELOG.md).

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
