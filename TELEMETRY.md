# Usage Telemetry

The documentdb-agent-kit installers (`scripts/install.ps1`, `scripts/install.sh`)
can send **anonymous, opt-in** usage telemetry so the maintainers can see which
skills are actually installed and prioritize accordingly.

## Opt-in only — off by default

Telemetry is **never** sent unless you explicitly enable it:

- PowerShell: `./scripts/install.ps1 -Target claude-user -Telemetry`
- Bash: `./scripts/install.sh --target claude-user --telemetry`
- Or set the environment variable `DDBKIT_TELEMETRY=1`.

If you do nothing, no network call is made. A telemetry failure never blocks or
fails an install.

## What is collected

A single `skill_install` event with these fields:

| Field | Example | Purpose |
|---|---|---|
| `kitVersion` | `1.0.0` | Which kit version was installed |
| `target` | `claude-user` | Which agent/target folder |
| `osFamily` | `windows` / `macos` / `linux` | Coarse platform mix |
| `method` | `copy` / `symlink` | How skills were installed |
| `skills` | `data-modeling,indexing,…` | Which skill folders were installed |
| `skillCount` | `16` | Number of skills installed |
| `invocationId` | random GUID | De-duplicate a single run; **not** stable across runs |

## What is NOT collected

- No file contents, source code, or query data.
- No connection strings, credentials, or App Insights keys.
- No usernames, hostnames, IP-derived identity, MAC addresses, or any stable
  machine/user identifier. `invocationId` is random per run and cannot be
  correlated across installs.

## Where it goes

Events are sent to an Azure Application Insights resource via its ingestion
endpoint (`https://dc.services.visualstudio.com/v2/track`). The installers ship
**without** a live key — the `INSTRUMENTATION_KEY` is a `<placeholder>`. To
enable telemetry against your own resource, provide an ingestion-only
instrumentation key through the `DDBKIT_AIKEY` environment variable:

```bash
DDBKIT_AIKEY="<your-instrumentation-key>" ./scripts/install.sh --target claude-user --telemetry
```

If no key is configured, the installer skips the telemetry send even when
`--telemetry` is passed.

## Opting out permanently

Simply never pass `--telemetry` / `-Telemetry` and leave `DDBKIT_TELEMETRY`
unset (or set it to `0`). You can also delete the telemetry block at the bottom
of the install scripts.
