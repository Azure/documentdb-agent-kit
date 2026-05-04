# documentdb-agent-kit

A bundle of agent skills + an MCP server for **Azure DocumentDB (MongoDB-compatible)** — the fully managed Azure service built on the open-source [DocumentDB](https://github.com/documentdb/documentdb) project (Postgres-backed, 99.03% MongoDB-compatible).

Skills follow the [Agent Skills](https://agentskills.io/) format and the kit ships with plugin manifests for Claude Code, Cursor, Codex, Gemini CLI, and GitHub Copilot.

👉 **Capabilities and skill catalog:** [`SKILLS.md`](SKILLS.md)

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

### Skills only (no MCP server)

If you only want the skill catalog without the MCP server, point your agent at the `skills/` directory. Per-agent shortcuts:

```bash
# Claude Code, project-scoped
mkdir -p .claude && ln -s "$(pwd)/skills" .claude/skills

# Claude Code, user-scoped
mkdir -p ~/.claude/skills
for d in skills/*/; do ln -s "$(pwd)/$d" ~/.claude/skills/; done
```

On Windows / PowerShell, use `New-Item -ItemType SymbolicLink` or copy the folder.

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
