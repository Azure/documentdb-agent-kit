# documentdb-agent-kit

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
server into every detected MCP client. This is the recommended path today —
the per-agent plugin/extension marketplaces below are still being published.

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
irm https://raw.githubusercontent.com/Azure/documentdb-agent-kit/main/install.ps1 -OutFile $env:TEMP\install.ps1
& $env:TEMP\install.ps1 -Uninstall -Yes
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

### Coming soon: per-agent plugin / extension marketplaces

The kit ships plugin manifests for Claude Code, Cursor, Codex, and Gemini CLI
(under `.claude-plugin/`, `.cursor-plugin/`, `.codex-plugin/`,
`gemini-extension.json`). The native marketplace install commands below are
**not yet published** — use the one-liner installer above in the meantime.

<!--
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
-->

### Universal one-liner — skills only (no MCP server)

To install just the skill catalog into whichever agent you're using, via the [skills.sh](https://skills.sh/) CLI:

```bash
npx skills add Azure/documentdb-agent-kit
```

This drops the rule docs into your agent's skill directory but **does not** install the MCP server. Use the [one-liner installer above](#one-liner-recommended) if you want the DB tools too.

> 💡 **Accept the optional `find-skills` helper when prompted.** During `npx skills add` the installer will ask whether to install [`find-skills`](https://github.com/skills-sh/find-skills) — say **yes**. It's a tiny meta-skill that lets agents auto-discover the right DocumentDB skill for a task (e.g. *"how do I create a BM25 index?"* → auto-loads `documentdb-full-text-search`) instead of relying on you to invoke skills by name. It's especially useful here because the kit ships 17 skills, more than agents reliably route on their own from `AGENTS.md` alone. If you skipped it, re-run `npx skills add find-skills` to add it later.

## Updating the kit

New skills, rule fixes, and MCP-server updates are released on `main`. Installs do **not** auto-update — each install path has its own refresh command. Run these when you want to pull in new features or fixes:

| Install path | Update command |
|---|---|
| One-liner installer (recommended) | re-run the `install.sh` / `install.ps1` curl one-liner with the same connection string (idempotent: refreshes the kit clone, rebuilds the MCP server, and re-merges the `DocumentDB` entry into every detected client config). Pin a specific ref with `--kit-ref <ref>` and/or `--mcp-ref <ref>`. |
| Skills only (skills.sh CLI) | re-run `npx skills add Azure/documentdb-agent-kit` |

<!--
Per-agent update commands (will be uncommented once plugin install paths are published):

| Install path | Update command |
|---|---|
| Claude Code | `/plugin update documentdb@azure-documentdb` |
| Cursor | re-run `/add-plugin azure/documentdb-agent-kit` |
| Codex | `codex plugin update documentdb` |
| Gemini CLI | `gemini extensions update documentdb-agent-kit` |
| GitHub Copilot CLI | `/plugin update https://github.com/Azure/documentdb-agent-kit.git` (or uninstall + reinstall) |
-->


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
