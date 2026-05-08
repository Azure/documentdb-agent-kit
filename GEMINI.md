# Azure DocumentDB Gemini Extension

This extension provides tools for managing and optimizing Azure DocumentDB (MongoDB-compatible) deployments using the official `documentdb-mcp-server`.

## Configuration

The extension requires a connection profile to be configured server-side. Set the `DOCUMENTDB_CONNECTION_PROFILES` environment variable before launching Gemini CLI.

### Recommended: Microsoft Entra / OIDC backend authentication

```bash
export DOCUMENTDB_CONNECTION_PROFILES='{"sandbox":{"authMode":"entra","endpoint":"<cluster>.mongocluster.cosmos.azure.com","tokenScope":"https://ossrdbms-aad.database.windows.net/.default","allowedHosts":["*.mongocluster.cosmos.azure.com"]}}'
```

Sign in with Azure CLI for local development:

```bash
az login --tenant <tenant-id>
```

In Azure hosting, use managed identity or workload identity and grant that identity access to the backend database.

### Local / sandbox: SCRAM connection string

```bash
export DOCUMENTDB_CONNECTION_PROFILES='{"local":{"uriEnv":"DOCUMENTDB_LOCAL_URI"}}'
export DOCUMENTDB_LOCAL_URI='mongodb://localhost:27017'
```

### Tool capability gates

By default only **read** tools are enabled. To enable higher-impact tools, override in your shell before launching Gemini:

```bash
export ENABLE_WRITE_TOOLS=true        # insert / update / delete / find_and_modify
export ENABLE_MANAGEMENT_TOOLS=true   # drop_database, drop_collection, create_index, ...
```

If the user needs help configuring the MCP server, use the `mcp-setup` skill to guide them through the process. For the full list of options, see the [DocumentDB MCP Server documentation](https://github.com/microsoft/documentdb-mcp).
