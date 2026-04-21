# Azure DocumentDB — Ready-to-deploy Bicep example

A no-agent-required deployment of an Azure DocumentDB cluster (`Microsoft.DocumentDB/mongoClusters`, API `2025-09-01`). Drop-in companion to the `documentdb-azure-deployment` skill.

## Contents

| File | Purpose |
|---|---|
| `main.bicep` | Parameterized cluster template (tier, storage, HA, firewall) |
| `main.parameters.sample.json` | Sample parameters file with a Key Vault secret reference |
| `deploy.sh` | Bash deploy script with preflight checks |
| `deploy.ps1` | PowerShell equivalent of `deploy.sh` |

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
# 1. Copy the sample and edit the values (cluster name, Key Vault ID, tier, HA mode)
cp main.parameters.sample.json main.parameters.json
$EDITOR main.parameters.json

# 2. Deploy
chmod +x ./deploy.sh
./deploy.sh rg-docdb-dev eastus2 main.parameters.json
```

**PowerShell (Windows):**

```powershell
Copy-Item main.parameters.sample.json main.parameters.json
code main.parameters.json  # or your editor

./deploy.ps1 -ResourceGroup rg-docdb-dev -Location eastus2 -ParametersFile main.parameters.json
```

If you omit the parameters file, the Azure CLI will interactively prompt you for `adminUsername` and `adminPassword` and use defaults for everything else.

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
