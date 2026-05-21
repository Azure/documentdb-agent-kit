---
name: documentdb-mcp-setup
description: Guide users through installing and configuring the DocumentDB MCP server for Azure DocumentDB. Use this skill when a user wants to wire the DocumentDB MCP server into an agentic client (Claude Code, Claude Desktop, Cursor, Copilot CLI, Gemini CLI, VS Code) and define a `CONNECTION_PROFILES` entry, or when they hit MCP connection / auth / profile errors.
---

# DocumentDB MCP Server Setup

This skill guides users through wiring the
[`microsoft/documentdb-mcp`](https://github.com/microsoft/documentdb-mcp)
server into an agentic client and pointing it at Azure DocumentDB (or another
MongoDB-compatible endpoint).

The DocumentDB MCP server is **stateless** and **administrator-controlled**:
backend connection details live in a `CONNECTION_PROFILES` JSON map defined in
the MCP client's config. Tools never accept a connection string as a runtime
argument — they reference a named profile via `connection_profile`.

## Fastest path: bundled installer

If the user wants the quickest path and is willing to run a script, point them
at the kit's installer, which installs both this skill pack and the MCP server
into every detected client in one command:

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/Azure/documentdb-agent-kit/main/install.sh | bash

# Windows (PowerShell)
irm https://raw.githubusercontent.com/Azure/documentdb-agent-kit/main/install.ps1 | iex
```

The installer prompts for a connection string, writes it as the `default`
profile, and configures all detected clients. The rest of this skill covers
the manual path (and is also the right reference when the installer fails or
the user wants to customize).

## Manual setup overview

Setup is per-client. For each client the user has installed:

1. Make sure Node.js 20+ is available (the MCP server runs on Node).
2. Find that client's MCP config file.
3. Add a `DocumentDB` server entry that launches the upstream MCP server and
   passes `CONNECTION_PROFILES` (and `TRANSPORT=stdio` + `ALLOW_UNAUTHENTICATED_STDIO=true`
   for local stdio use).
4. Restart the client.

## Step 1: Confirm prerequisites

```bash
node --version   # must be >= 20
git --version    # required by `npx -y github:microsoft/documentdb-mcp`
```

If either is missing, install them before continuing.

## Step 2: Pick the connection target

| Option | When to use | Example URI |
|---|---|---|
| **A. Azure DocumentDB** | Production / cloud dev | `mongodb+srv://<user>:<pw>@<cluster>.mongocluster.cosmos.azure.com/?tls=true&authMechanism=SCRAM-SHA-256` |
| **B. Local MongoDB / DocumentDB** | Local dev | `mongodb://localhost:27017` |
| **C. Custom MongoDB-compatible** | Atlas, self-hosted, third-party | `mongodb://<user>:<pw>@host:port/?tls=true` |

**Azure DocumentDB connection string:** Azure portal → your DocumentDB cluster
→ **Settings** → **Connection strings**. Replace `<username>` / `<password>`
with database user credentials. TLS is required (`tls=true` must be present).

## Step 3: Pick a transport

- **`stdio`** (default, recommended) — the client launches the server as a
  subprocess. Use this for every client below.
- **`streamable-http`** — only for browser clients or custom HTTP integrations
  where you have a separate, long-running server with Entra-authenticated
  bearer tokens. Not covered here; see the upstream README.

For stdio, `ALLOW_UNAUTHENTICATED_STDIO=true` is required (stdio runs on the
user's trusted local machine and bypasses Entra auth).

## Step 4: Write the MCP config

The MCP server entry has the same shape for every client. Only the wrapping
config file and the top-level key (`mcpServers` vs `mcp.servers`) differ.

**Server entry template** (substitute `<CONN_STRING>` with the URI from Step 2):

```jsonc
{
  "DocumentDB": {
    "command": "npx",
    "args": ["-y", "github:microsoft/documentdb-mcp"],
    "env": {
      "TRANSPORT": "stdio",
      "ALLOW_UNAUTHENTICATED_STDIO": "true",
      "CONNECTION_PROFILES": "{\"default\":{\"authMode\":\"connectionString\",\"uri\":\"<CONN_STRING>\"}}"
    }
  }
}
```

Notes:

- `CONNECTION_PROFILES` is a **JSON string** (escaped) — not a JSON object.
- The profile name `default` is what agents pass to tool calls via the
  `connection_profile` argument. You can use any name; `default` keeps it
  simple.
- To allow write or management tools, add `"ENABLE_WRITE_TOOLS": "true"` and/or
  `"ENABLE_MANAGEMENT_TOOLS": "true"` to `env`. Read tools are on by default.
- The first `npx -y github:...` invocation will clone and build the server
  (~30 s on a fast connection). Subsequent invocations use the `npx` cache.
  For faster startup, install once locally and point `command`/`args` at the
  built `node /path/to/dist/main.js` instead — this is what the bundled
  installer does.

### Client-specific config files

| Client | Config file | Top-level key |
|---|---|---|
| **Claude Code** (user-scoped) | `~/.claude.json` | `mcpServers` |
| **Claude Desktop** | macOS: `~/Library/Application Support/Claude/claude_desktop_config.json` <br> Linux: `~/.config/Claude/claude_desktop_config.json` <br> Windows: `%APPDATA%\Claude\claude_desktop_config.json` | `mcpServers` |
| **Cursor** (user-scoped) | `~/.cursor/mcp.json` | `mcpServers` |
| **GitHub Copilot CLI** | `~/.copilot/mcp-config.json` | `mcpServers` |
| **GitHub Copilot for VS Code** | VS Code `settings.json` | `mcp.servers` |
| **Gemini CLI** | `~/.gemini/settings.json` | `mcpServers` |

If the file doesn't exist yet, create it with a single top-level object:

```json
{ "mcpServers": { "DocumentDB": { ... } } }
```

If it already has other servers, **add** the `DocumentDB` entry inside the
existing `mcpServers` object — don't overwrite the whole file.

## Step 5: Restart the client and verify

1. **Fully quit** the client (not just close the window).
2. Reopen it.
3. Ask the agent to list available DocumentDB tools, or run a tool directly
   (the agent should pass `connection_profile: "default"`):
   - `list_databases` — confirms the server is reachable and the profile works
   - `db_stats` — basic round-trip check

## Troubleshooting

- **`npx` errors / repo not found**: the upstream `microsoft/documentdb-mcp`
  repo may be private or unreachable. Check `git ls-remote
  https://github.com/microsoft/documentdb-mcp.git`; if it fails, fall back to
  cloning the repo manually, running `npm install && npm run build`, and
  pointing `command` → `node`, `args` → `["<abs-path>/dist/main.js"]`.
- **`unauthenticated stdio is disabled`**: you forgot
  `ALLOW_UNAUTHENTICATED_STDIO: "true"` in `env`.
- **`connection_profile "default" not found`**: the agent is passing a
  different profile name than what's defined in `CONNECTION_PROFILES`. Either
  rename your profile or tell the agent which name to use.
- **TLS errors against Azure DocumentDB**: ensure `tls=true` is in the URI and
  the connection string is fully URL-encoded (special characters in passwords
  must be percent-encoded).
- **Auth errors**: verify the database user exists in Azure portal under your
  cluster's Settings → Authentication, and that the password is correct.
- **Connection timeout to Azure**: Azure DocumentDB firewall may be blocking
  your IP. Portal → cluster → **Networking** → add your client IP to the
  allowlist.
- **JSON escape issues**: `CONNECTION_PROFILES` is a string of JSON. Inner
  double quotes must be escaped (`\"`). Use a JSON validator if the client
  silently ignores the server. The bundled installer handles escaping
  correctly — prefer it if escaping is painful.
- **VS Code uses `mcp.servers`, not `mcpServers`**: this is the one client
  with a different top-level key.
