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

## Safety: never receive credentials in chat

The DocumentDB connection string is a **secret** — it contains a username and
password that grant database access. The agent MUST follow these rules:

1. **Never ask the user to paste a connection string, password, or token into
   the chat.** Always instruct the user to add the value directly to their
   local MCP config file themselves (or run the bundled installer, which
   prompts via stdin instead of chat).
2. **Never read, echo, log, or repeat back a credential** the user pasted by
   mistake. If the user pastes one anyway, respond with: "I won't process that
   value — please delete it from the chat history and add it directly to your
   client's MCP config instead," and continue with placeholders only. The
   agent itself cannot remove messages it has already received — only the
   user can delete the message from their chat history.
3. **Never run a shell command that would print a credential to stdout.**
4. **Never write the credential to any file the agent itself creates or
   edits.** The agent only writes placeholder `[USER]:[PASSWORD]@...` (square
   brackets defeat the `mongodb://[^:]+:[^@]+@` secret-scanner regex); the
   user replaces it locally.
5. **Never include a credential in a generated explanation, summary, commit
   message, or example.** Use `<redacted>` if you must reference its position.

If any step below appears to require a credential value, treat it as a
placeholder for the user to fill in locally.

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
   passes `CONNECTION_PROFILES` (and `TRANSPORT=stdio` + `AUTH_REQUIRED=false`
   + `TRUST_LOCAL_STDIO=true` for local stdio use).
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

For stdio, set `AUTH_REQUIRED=false` and `TRUST_LOCAL_STDIO=true`.
The server defaults `AUTH_REQUIRED=true` and **exits at startup** unless
`ENTRA_TENANT_ID` / `ENTRA_AUDIENCE` are set, even for stdio.
(`TRUST_LOCAL_STDIO` was named `ALLOW_UNAUTHENTICATED_STDIO` before
[microsoft/documentdb-mcp#83](https://github.com/microsoft/documentdb-mcp/pull/83)
— if you're on an older server build, use that name instead.)

**`AUTH_REQUIRED=false` does not weaken your cluster's auth.** It gates only
the Entra-JWT bearer-token check on the MCP server's HTTP/SSE transport —
i.e., calls from the MCP client to this server. It is fully independent
from how the MCP server talks to your DocumentDB cluster: SCRAM
username/password (from the connection-string URI) and Entra-to-cluster
tokens (`authMode: "entra"`) flow through `CONNECTION_PROFILES` and stay
active regardless of `AUTH_REQUIRED`. TLS to the cluster (`tls=true`),
capability gates (`ENABLE_*_TOOLS`), and tool-tier authorization are also
unaffected.

This setup is safe **only because `TRANSPORT=stdio`**: the MCP server runs
as a subprocess of the trusted local client — no network listener is
opened. If you ever switch `TRANSPORT` to `streamable-http` or `sse`, set
`AUTH_REQUIRED=true` and provide the Entra tenant/audience, or the `/mcp`
endpoint will be exposed unauthenticated.

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
      "AUTH_REQUIRED": "false",
      "TRUST_LOCAL_STDIO": "true",
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
- **`stdio transport is disabled when AUTH_REQUIRED=true` / `unauthenticated stdio is disabled`**:
  you forgot `TRUST_LOCAL_STDIO: "true"` in `env` (or, on older builds before
  microsoft/documentdb-mcp#83, `ALLOW_UNAUTHENTICATED_STDIO: "true"`).
- **`AUTH_REQUIRED is true but ...` / server exits immediately on launch**:
  add `"AUTH_REQUIRED": "false"` to `env`. The server defaults this to `true`
  and refuses to start without Entra tenant/audience config. This flag gates
  only the Entra-JWT bearer check on the MCP server's HTTP/SSE transport
  — it does **not** disable MongoDB-level auth (SCRAM or `authMode=entra`),
  TLS, or capability gates. Only set it to `false` together with
  `TRANSPORT=stdio`.
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
- **Client doesn't pick up the new server**: ensure a full restart of the
  client (quit + reopen), not just a window reload.
- **VS Code uses `mcp.servers`, not `mcpServers`**: this is the one client
  with a different top-level key.
