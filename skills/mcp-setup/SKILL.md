---
name: documentdb-mcp-setup
description: Guide users through configuring the DocumentDB MCP server for Azure DocumentDB. Use this skill when a user has the DocumentDB MCP server installed but hasn't configured the required environment variables, or when they ask about connecting to Azure DocumentDB and don't have the credentials set up.
---

# DocumentDB MCP Server Setup

This skill guides users through configuring the DocumentDB MCP server for use
with an agentic client, targeting Azure DocumentDB.

## Overview

The DocumentDB MCP server requires a connection string to your Azure DocumentDB
cluster. Users have three options:

1. **Azure DocumentDB Connection String** (Option A): Direct connection to
   an Azure DocumentDB cluster
   - Recommended for most users
   - Requires `DOCUMENTDB_URI` environment variable
   - Connection string from Azure portal

2. **Local MongoDB** (Option B): Connect to a local MongoDB instance for
   development
   - Best for local testing — minimal configuration required
   - Uses default `mongodb://localhost:27017`
   - No Azure credentials needed

3. **Custom MongoDB-compatible endpoint** (Option C): Connect to any
   MongoDB-compatible database
   - For self-hosted MongoDB, other DocumentDB-compatible services, or
     MongoDB Atlas
   - Requires `DOCUMENTDB_URI` environment variable with custom connection string

This is an interactive step-by-step guide. The agent detects the user's
environment and provides tailored instructions.

## Step 1: Check Existing Configuration

Before starting the setup, check if the user already has the required
environment variables configured.

Run this command to check for existing configuration (masking values to avoid
exposing credentials):

```bash
env | grep "^DOCUMENTDB_URI\|^TRANSPORT\|^HOST\|^PORT" | sed 's/DOCUMENTDB_URI=.*/DOCUMENTDB_URI=[set]/'
```

**Interpretation:**

- If `DOCUMENTDB_URI` is set → connection is already configured
- If `TRANSPORT` is set → transport mode is configured
- If neither is set → proceed with full setup

**Partial Configuration Handling:**

- User already has `DOCUMENTDB_URI` set and just wants to change transport →
  skip to Step 4
- User wants to switch connection targets → proceed with Steps 2–5
- User wants to update credentials → skip to Step 5 (profile editing
  instructions)

## Step 2: Present Configuration Options

If no valid configuration exists, present the options:

**Azure DocumentDB (Option A)** — Best for:

- Production and development with Azure DocumentDB
- Full MongoDB wire protocol compatibility
- Managed database with Azure integration

**Local MongoDB (Option B)** — Best for:

- Local development and testing without cloud setup
- Fastest setup, no credentials required
- Just uses `mongodb://localhost:27017`

**Custom Endpoint (Option C)** — Best for:

- Self-hosted MongoDB deployments
- MongoDB Atlas or other MongoDB-compatible services
- Non-standard connection configurations

Ask the user which option they'd like to proceed with.

## Step 3a: Azure DocumentDB Setup

If the user chooses Option A:

### 3a.1: Explain How to Find the Connection String

1. Go to the [Azure portal](https://portal.azure.com)
2. Navigate to your Azure DocumentDB cluster
3. In the left menu, select **Settings** → **Connection strings**
4. Copy the connection string — it will look like:
   `mongodb+srv://<username>:<password>@<cluster-name>.mongocluster.cosmos.azure.com/?tls=true&authMechanism=SCRAM-SHA-256`
5. Replace `<username>` and `<password>` with your database user credentials

**Expected formats:**

- `mongodb+srv://<user>:<password>@cluster.mongocluster.cosmos.azure.com/?tls=true&authMechanism=SCRAM-SHA-256`
- `mongodb://<user>:<password>@cluster.mongocluster.cosmos.azure.com:10255/?tls=true&authMechanism=SCRAM-SHA-256`

**Important**: Azure DocumentDB requires TLS. Ensure `tls=true` is in the
connection string.

Proceed to Step 4 (Configure Transport Mode).

## Step 3b: Local MongoDB Setup

If the user chooses Option B:

### 3b.1: Verify Local MongoDB is Running

```bash
mongosh --eval "db.runCommand({ping: 1})" 2>/dev/null || echo "MongoDB not reachable"
```

If MongoDB is not installed or running, direct them to:
https://www.mongodb.com/docs/manual/installation/

The default connection string `mongodb://localhost:27017` will be used. No
`DOCUMENTDB_URI` environment variable is needed (it's the server default).

Proceed to Step 4 (Configure Transport Mode).

## Step 3c: Custom Endpoint Setup

If the user chooses Option C:

Ask the user for their MongoDB-compatible connection string.

**Expected formats:**

- `mongodb://<user>:<password>@host:port/database`
- `mongodb+srv://<user>:<password>@host/database`
- `mongodb://host:port` (no auth)

Proceed to Step 4 (Configure Transport Mode).

## Step 4: Configure Transport Mode

The DocumentDB MCP server supports two transport modes:

**stdio (Default)** — Recommended for most MCP client integrations:
- Communicates over standard input/output streams
- No additional configuration needed
- Best for Claude, Cursor, Copilot CLI, and most coding agents

**streamable-http** — For HTTP-based integrations:
- Runs as an HTTP server
- Configurable host and port
- Best for browser-based clients or custom HTTP integrations

For most users, **stdio** is the right choice. Only choose streamable-http if
you specifically need HTTP-based access.

If streamable-http is chosen, also configure:
- `HOST` — Server host (default: `localhost`)
- `PORT` — Server port (default: `8070`)

Proceed to Step 5 (Update Shell Profile).

## Step 5: Update Shell Profile

Help the user add the environment variables to their shell profile. **Do not ask
for or handle credentials** — provide exact instructions so the user can add
them directly.

### 5.1: Detect Shell and Profile File

If the user is on Windows, assume **PowerShell** but ask the user to confirm.
For Unix/macOS, detect the shell:

```bash
echo $SHELL
```

Based on the result, identify the appropriate profile file.

### 5.2: Show the Exact Snippet to Add

Tell the user to store the connection string in a dedicated `~/.documentdb-env`
file. This keeps credentials out of files that are often group/world readable by
default and prevents accidentally committing them to git.

**Step 1**: Create/edit `~/.documentdb-env` (e.g., `nano ~/.documentdb-env`)
and add:

**For Azure DocumentDB (Option A):**

```bash
# DocumentDB MCP Server Configuration
export DOCUMENTDB_URI="<paste-your-connection-string-here>"
```

**For Custom Endpoint (Option C):**

```bash
# DocumentDB MCP Server Configuration
export DOCUMENTDB_URI="<paste-your-connection-string-here>"
```

**If streamable-http transport was chosen (Step 4), also add:**

```bash
export TRANSPORT="streamable-http"
export HOST="localhost"
export PORT="8070"
```

**Step 2**: Restrict permissions on the file:

```bash
chmod 600 ~/.documentdb-env
```

**Step 3**: Source the file from the shell profile. Tell the user to open their
profile file (e.g., `code ~/.zshrc`, `nano ~/.zshrc`) and add:

```bash
source ~/.documentdb-env
```

Adjust syntax for the detected shell (e.g., for fish: `bass source
~/.documentdb-env` or set variables directly with `set -x`; for PowerShell:
dot-source a `.ps1` file instead).

### 5.3: After Editing — Reload and Verify

Once the user has saved the file, provide the commands to reload and verify:

**Reload the profile:**

```bash
source ~/.zshrc  # adjust path to match their profile file
```

**Verify the variables are set (masking values):**

```bash
env | grep "^DOCUMENTDB_URI\|^TRANSPORT\|^HOST\|^PORT" | sed 's/DOCUMENTDB_URI=.*/DOCUMENTDB_URI=[set]/'
```

Expected output should show the variable name(s) they just added.

Proceed to Step 6 (Next Steps).

## Step 6: Next Steps

### For Options A & C (Azure DocumentDB / Custom Endpoint):

1. **Restart the agentic client**: Fully quit the client, then in your terminal
   run `source <profile-file>` (e.g., `source ~/.zshrc`) to load the new
   variables. Open the client from that same shell session so it inherits the
   environment.

2. **Verify MCP Server**: After restart, test by performing a DocumentDB
   operation:
   - Try `list_databases` to see available databases
   - Try `get_connection_status` to verify the connection

3. **Using the Tools**:
   - Database operations: `list_databases`, `db_stats`, `get_db_info`
   - Collection operations: `collection_stats`, `sample_documents`
   - Document operations: `find_documents`, `count_documents`, `aggregate`
   - Index operations: `list_indexes`, `index_stats`, `create_index`
   - Query optimization: `optimize_find_query`, `explain_aggregate_query`

### For Option B (Local MongoDB):

1. **Ready to use**: No additional configuration needed if using the default
   connection string.

2. **Start the MCP server**: The server will connect to `mongodb://localhost:27017`
   by default.

3. **Verify**: Try `list_databases` to confirm connectivity.

## Troubleshooting

- **Variables not appearing after `source`**: Check the profile file path and
  confirm the file was saved
- **Client doesn't pick up variables**: Ensure full restart (quit + reopen),
  not just a reload
- **TLS errors with Azure DocumentDB**: Ensure `tls=true` is in the
  connection string
- **Authentication errors**: Verify username and password in the connection
  string are correct; check that the user exists in Azure portal
- **Connection timeout**: Check network connectivity and firewall rules;
  Azure DocumentDB may require allowlisting your IP in the Azure portal
  under Networking settings
- **fish/PowerShell**: Syntax differs — use `set -x` (fish) or `$env:`
  (PowerShell) instead of `export`
