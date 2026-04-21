---
name: documentdb-azure-deployment
description: Deploy an Azure DocumentDB cluster (`Microsoft.DocumentDB/mongoClusters`) end-to-end — Bicep (primary), Azure CLI one-shot, Terraform, or portal. Covers resource-group creation, cluster parameters (tier, storage, server version, sharding, HA), firewall rule configuration, retrieving the connection string, and teardown. Use when the user asks to provision, create, deploy, or spin up an Azure DocumentDB cluster, or wants infrastructure-as-code for one.
license: MIT
---

# Deploy Azure DocumentDB

Interactive skill for provisioning a managed **Azure DocumentDB** cluster (resource type `Microsoft.DocumentDB/mongoClusters`, API `2025-09-01`). Azure DocumentDB is the managed Azure service built on the open-source [`microsoft/documentdb`](https://github.com/microsoft/documentdb) engine.

For running DocumentDB locally instead (Docker / Compose), use `documentdb-local-deployment`. For connection-string tuning after the cluster exists, use `documentdb-connection`.

## Step 1 — gather inputs

Before generating any template or command, confirm with the user:

| Input | Example | Notes |
|---|---|---|
| Subscription | `11111111-...` | Use `az account show` to verify the active one |
| Resource group | `rg-documentdb-dev` | Create it (or reuse) |
| Location | `eastus2`, `westeurope` | Must be a [supported region](https://learn.microsoft.com/azure/documentdb/) |
| Cluster name | `docdb-prod-001` | 8–40 chars, lowercase letters/digits/hyphens; globally unique in Azure |
| Admin username | `clusteradmin` | Avoid reserved names like `admin`, `root` |
| Admin password | — | 8–128 chars; store in Key Vault — **never commit** |
| Compute tier | `M10` (dev) / `M30`+ (prod) | Full list: `M10`, `M20`, `M30`, `M40`, `M50`, `M60`, `M80`, `M200` |
| Storage per shard (GiB) | `32` (dev) / `128`+ (prod) | |
| Shard count | `1` (auto-shard up to TB scale — see `documentdb-cluster-sharding`) | |
| High availability | `Disabled` (dev) / `SameZone` or `ZoneRedundant` (prod) | HA requires M30+ |
| MongoDB server version | `8.0` | |
| Public network access | Default `Enabled` with firewall rules | Or disable and attach Private Endpoint (see `documentdb-security`) |

If the user didn't specify production vs dev, ask — the tier, HA, and firewall posture differ sharply.

## Step 2 — choose a deployment path

| Path | Use when | Section |
|---|---|---|
| **Bicep** (recommended) | Repeatable infra-as-code, PR-reviewed, committed to repo | [Step 3a](#step-3a--deploy-with-bicep) |
| **Azure CLI one-shot** | Prototype, local dev, quick validation | [Step 3b](#step-3b--deploy-with-azure-cli-one-shot) |
| **Terraform** | Existing Terraform estate | [Step 3c](#step-3c--deploy-with-terraform) |
| **Portal** | First-time users who want to see the UI | [Azure portal quickstart](https://learn.microsoft.com/azure/documentdb/quickstart-portal) |

For Bicep, load `references/bicep-cluster-template.md` — it contains the canonical parameterized template and an optional private-endpoint variant.

## Step 3a — deploy with Bicep

Generate `main.bicep` using the template in `references/bicep-cluster-template.md`, then:

```bash
# 1. Sign in + select subscription
az login
az account set --subscription "<subscription-name-or-id>"

# 2. Create the resource group
az group create \
  --name "<resource-group-name>" \
  --location "<location>"

# 3. Deploy — you'll be prompted for adminUsername / adminPassword
az deployment group create \
  --resource-group "<resource-group-name>" \
  --template-file main.bicep

# Non-interactive: use a parameters file (do NOT commit passwords)
az deployment group create \
  --resource-group "<resource-group-name>" \
  --template-file main.bicep \
  --parameters @main.parameters.json
```

**Secret handling.** Never hardcode `adminPassword` in `main.parameters.json` or a repo. Options:

- Reference Key Vault from the parameters file:
  ```json
  {
    "adminPassword": {
      "reference": {
        "keyVault": { "id": "/subscriptions/.../vaults/kv-documentdb" },
        "secretName": "docdb-admin-password"
      }
    }
  }
  ```
- Or pass inline from the shell's own secret source: `--parameters adminPassword="$(az keyvault secret show ... --query value -o tsv)"`.

## Step 3b — deploy with Azure CLI one-shot

For quick iteration without a Bicep file:

```bash
az login
az account set --subscription "<subscription-name-or-id>"
az group create --name rg-docdb-dev --location eastus2

# Deploy the cluster via az resource create against the 2025-09-01 API
az resource create \
  --resource-group rg-docdb-dev \
  --name docdb-dev-001 \
  --resource-type "Microsoft.DocumentDB/mongoClusters" \
  --api-version 2025-09-01 \
  --location eastus2 \
  --properties '{
    "administrator": { "userName": "clusteradmin", "password": "REPLACE_WITH_STRONG_PASSWORD" },
    "serverVersion": "8.0",
    "sharding":       { "shardCount": 1 },
    "storage":        { "sizeGb": 32 },
    "highAvailability": { "targetMode": "Disabled" },
    "compute":        { "tier": "M10" }
  }'

# Add a firewall rule — "Allow Azure services" shortcut uses 0.0.0.0 for both start and end
az resource create \
  --resource-group rg-docdb-dev \
  --name "docdb-dev-001/AllowAllAzureServices" \
  --resource-type "Microsoft.DocumentDB/mongoClusters/firewallRules" \
  --api-version 2025-09-01 \
  --properties '{ "startIpAddress": "0.0.0.0", "endIpAddress": "0.0.0.0" }'
```

Never paste a real password on the command line in shared terminals — read it from an env var or Key Vault.

## Step 3c — deploy with Terraform

Prefer this when the user already uses Terraform. The `azurerm` provider supports `azurerm_cosmosdb_mongo_cluster` / equivalent `Microsoft.DocumentDB/mongoClusters` resource. Full quickstart: https://learn.microsoft.com/azure/documentdb/quickstart-terraform — the same parameters as Step 1 apply.

## Step 4 — verify the deployment

```bash
az resource list \
  --resource-group "<resource-group-name>" \
  --namespace Microsoft.DocumentDB \
  --resource-type mongoClusters \
  --query "[].name" \
  --output json
```

Expect one entry matching your cluster name.

## Step 5 — retrieve the connection string

From the portal: **cluster → Connection strings**. The returned string has a `<password>` placeholder you must substitute.

Form of the connection string:

```
mongodb+srv://<user>:<password>@<cluster>.global.mongocluster.cosmos.azure.com/?tls=true&authMechanism=SCRAM-SHA-256&retrywrites=false&maxIdleTimeMS=120000
```

Note `retrywrites=false` — Azure DocumentDB does not support retryable writes; leaving it at the driver default will cause connection errors (see `documentdb-connection` for driver-specific tuning).

## Step 6 — configure access

Pick one posture and help the user apply it:

- **Public + firewall** (dev only). Add the developer's IP:
  ```bash
  MY_IP=$(curl -s https://api.ipify.org)
  az resource create \
    --resource-group rg-docdb-dev \
    --name "docdb-dev-001/dev-$(whoami)" \
    --resource-type "Microsoft.DocumentDB/mongoClusters/firewallRules" \
    --api-version 2025-09-01 \
    --properties "{ \"startIpAddress\": \"$MY_IP\", \"endIpAddress\": \"$MY_IP\" }"
  ```
  The `0.0.0.0`–`0.0.0.0` rule is the documented shortcut for "Allow Azure services and resources within Azure" — use for serverless workloads. Never leave `0.0.0.0–255.255.255.255` in place outside a short connection test.

- **Private Endpoint** (prod). See `documentdb-security` — public access should be disabled and a Private DNS zone added.

- **Entra RBAC / CMK / diagnostic settings**. See `documentdb-security` and `documentdb-monitoring`.

## Step 7 — teardown

```bash
az group delete --name "<resource-group-name>" --yes --no-wait
```

Confirm with the user before running — this removes everything in the resource group, not just the cluster.

## References

- [Quickstart: Deploy an Azure DocumentDB cluster using Bicep](https://learn.microsoft.com/azure/documentdb/quickstart-bicep)
- [Quickstart: Create an Azure DocumentDB cluster by using the Azure portal](https://learn.microsoft.com/azure/documentdb/quickstart-portal)
- [`Microsoft.DocumentDB/mongoClusters` resource reference](https://learn.microsoft.com/azure/templates/microsoft.documentdb/mongoclusters)
- Loaded as needed: `references/bicep-cluster-template.md`

## Related skills

- `documentdb-local-deployment` — Docker / Compose for running DocumentDB locally
- `documentdb-connection` — connection-string tuning after the cluster exists
- `documentdb-security` — Private Endpoint, Entra RBAC, CMK
- `documentdb-cluster-sharding` — M-tier selection, shard-key design at TB scale
- `documentdb-high-availability` — HA, cross-region replica, SLA tiers
- `documentdb-monitoring` — diagnostic settings, slow-query logs
