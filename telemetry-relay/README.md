# Telemetry relay (Azure Function)

A tiny serverless relay that forwards **anonymous, opt-in** install events from
the documentdb-agent-kit installers to Application Insights, so the App Insights
connection string **never ships in the public repo or the client**.

```
installer (install.ps1/.sh)  ──POST──▶  this Function (/api/collect)  ──▶  Application Insights  ──▶  Grafana (Azure Monitor data source)
   ships only a public URL              holds the connection string
                                        in app settings (server-side)
```

## What's here

| File | Purpose |
|---|---|
| `src/functions/collect.js` | HTTP-triggered relay: validates, allow-lists, rate-limits, forwards `trackEvent` |
| `host.json` | Functions host config |
| `package.json` | `@azure/functions` v4 + `applicationinsights` SDK |
| `main.bicep` | Deploys Log Analytics + App Insights + Function App + storage |
| `local.settings.json.sample` | Copy to `local.settings.json` for local runs (git-ignored) |

## Prerequisites

- Azure CLI (`az`), Azure Functions Core Tools (`func`), Node.js 20+
- An Azure subscription + permission to create resources

## 1. Deploy the infrastructure

```powershell
az login
az account set --subscription "<your-subscription-id>"

$rg = "documentdb-telemetry-rg"
az group create -n $rg -l westus2

az deployment group create -g $rg -f telemetry-relay/main.bicep -p namePrefix=ddbkit
```

Note the outputs — especially `collectUrl` (the endpoint the installers POST to)
and `appInsightsName` (used by the Grafana data source).

## 2. Publish the Function code

```powershell
cd telemetry-relay
npm install

# Function App name = the 'funcName' output from the deployment
func azure functionapp publish <ddbkit-func-xxxxxx>
```

## 3. Test locally (optional)

```powershell
Copy-Item local.settings.json.sample local.settings.json
# paste your App Insights connection string into local.settings.json (git-ignored)
npm install
func start
# in another shell:
curl -X POST http://localhost:7071/api/collect -H "Content-Type: application/json" `
  -d '{"name":"skill_install","properties":{"kitVersion":"1.0.0","osFamily":"windows","skills":"indexing,vector-search"},"measurements":{"skillCount":2}}'
```

## 4. Point the installers at the relay

Set the relay URL in the installers (or via env var) instead of calling App
Insights directly — only the **URL** is public, never a key:

```powershell
./scripts/install.ps1 -Target claude-user -Telemetry -RelayUrl "https://<collectUrl>"
```

## 5. Grafana

Add an **Azure Monitor** data source in Grafana (managed identity + Monitoring
Reader), then query the custom events with KQL, e.g.:

```kusto
customEvents
| where name == "skill_install"
| mv-expand skill = split(tostring(customDimensions.skills), ",")
| summarize installs = count() by tostring(skill)
| order by installs desc
```

## Security notes

- The **connection string is only in Function app settings** (set by Bicep) — not
  in this repo, not in the shipped installers.
- The endpoint is public, so the relay **allow-lists** event/property names, caps
  body size, and applies a best-effort per-IP rate limit. Tune these in
  `src/functions/collect.js`.
- The relay never returns client-visible errors (always `202`) so telemetry can't
  break an install.
- Set an App Insights **daily cap** to bound cost against abuse.
