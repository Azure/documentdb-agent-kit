# Azure DocumentDB — Ready-to-deploy Bicep example

A no-agent-required deployment of an Azure DocumentDB cluster (`Microsoft.DocumentDB/mongoClusters`, API `2025-09-01`). Drop-in companion to the `documentdb-azure-deployment` skill.

## Contents

| File | Purpose |
|---|---|
| `main.bicep` | Parameterized cluster template (tier, storage, HA, firewall) |
| `main.parameters.sample.json` | **Production-default** sample: M30 + ZoneRedundant HA + 128 GiB, Key Vault secret reference |
| `main.parameters.dev.json` | **Dev/prototype** sample: M10 + HA Disabled + 32 GiB |
| `deploy.sh` | Bash deploy script with preflight checks + confirm prompt |
| `deploy.ps1` | PowerShell equivalent of `deploy.sh` |

## Defaults (important)

`main.bicep` ships with **production-safe defaults**: `computeTier = M30`, `haTargetMode = ZoneRedundant`, `storageSizeGb = 128`. A `./deploy.sh <rg> <location>` with no parameters file produces a real production-class cluster — not a free tier.

For dev/prototype use, pass `main.parameters.dev.json` (M10, HA Disabled, 32 GiB) or override individual parameters on the CLI:

```bash
az deployment group create -g <rg> -f main.bicep \
  --parameters computeTier=M10 storageSizeGb=32 haTargetMode=Disabled
```

## Prerequisites

- An Azure subscription with **Contributor** or **Owner** role on the target resource group
- Azure CLI 2.60 or later — [install](https://learn.microsoft.com/cli/azure/install-azure-cli)
- (Recommended) An Azure Key Vault holding the admin password as a secret, referenced from the parameters file

The deploy scripts run these checks automatically before attempting deployment:

1. `az` is on `PATH`
2. You are signed in (`az account show`); if not, it launches `az login`
3. `Microsoft.DocumentDB` provider is registered on your subscription (registers it if not)
4. The target resource group exists (creates it if not)

## Quick start

**Bash / macOS / Linux / WSL:**

```bash
# Production (defaults from main.bicep: M30 + ZoneRedundant HA + 128 GiB)
cp main.parameters.sample.json main.parameters.json
$EDITOR main.parameters.json              # set clusterName + Key Vault ID
chmod +x ./deploy.sh
./deploy.sh rg-docdb-prod eastus2 main.parameters.json

# Dev / prototype (M10 + HA Disabled + 32 GiB)
./deploy.sh rg-docdb-dev eastus2 main.parameters.dev.json
```

**PowerShell (Windows):**

```powershell
Copy-Item main.parameters.sample.json main.parameters.json
code main.parameters.json

./deploy.ps1 -ResourceGroup rg-docdb-prod -Location eastus2 -ParametersFile main.parameters.json
```

If you omit the parameters file, the Azure CLI interactively prompts for `adminUsername` and `adminPassword`; the scripts show the Bicep defaults and ask you to confirm before deploying. Pass `SKIP_CONFIRM=1 ./deploy.sh ...` (bash) or `-SkipConfirm` (PowerShell) to automate.

## Production notes

- **Secrets.** Never commit a real password in `main.parameters.json`. Use the Key Vault reference in the sample file, or pass the password inline from your shell's own secret source.
- **HA.** Set `haTargetMode` to `SameZone` or `ZoneRedundant`. Requires `computeTier` M30 or higher.
- **Firewall.** The default `allowAzureServices: true` adds the documented `0.0.0.0–0.0.0.0` shortcut rule ("Allow Azure services and resources within Azure to access this cluster"). For production with Private Endpoint, set `allowAzureServices: false` and follow the Private Endpoint pattern in `skills/azure-deployment/references/bicep-cluster-template.md`.
- **Provider registration.** `Microsoft.DocumentDB` registration is subscription-wide and only needs to happen once.

## After deployment

Retrieve the connection string:

```bash
az resource show \
  --resource-group rg-docdb-dev \
  --name docdb-dev-001 \
  --resource-type Microsoft.DocumentDB/mongoClusters \
  --api-version 2025-09-01 \
  --query "properties.connectionString" \
  --output tsv
```

The returned string contains a literal `<password>` placeholder — substitute your admin password (or read it from Key Vault) before using it.

Then see `skills/connection/SKILL.md` for driver-side pool/timeout/retry tuning.

## References

- [Quickstart: Deploy an Azure DocumentDB cluster using Bicep](https://learn.microsoft.com/azure/documentdb/quickstart-bicep)
- [`Microsoft.DocumentDB/mongoClusters` resource reference](https://learn.microsoft.com/azure/templates/microsoft.documentdb/mongoclusters)
- Skill: `skills/azure-deployment/SKILL.md` (agent-driven end-to-end workflow)
