---
name: documentdb-azure-deployment
description: Deploy an Azure DocumentDB cluster (`Microsoft.DocumentDB/mongoClusters`) end-to-end — Bicep (primary), Azure CLI one-shot, Terraform, or portal. Covers resource-group creation, cluster parameters (tier, storage, server version, sharding, HA), firewall rule configuration, retrieving the connection string, and teardown. Use when the user asks to provision, create, deploy, or spin up an Azure DocumentDB cluster, or wants infrastructure-as-code for one.
license: MIT
---

# Deploy Azure DocumentDB

Interactive skill for provisioning a managed **Azure DocumentDB** cluster (resource type `Microsoft.DocumentDB/mongoClusters`, API `2025-09-01`). Azure DocumentDB is the managed Azure service built on the open-source [`microsoft/documentdb`](https://github.com/microsoft/documentdb) engine.

For running DocumentDB locally instead (Docker / Compose), use `documentdb-local-deployment`. For connection-string tuning after the cluster exists, use `documentdb-connection`.

> **No-agent shortcut.** A ready-to-run Bicep + deploy script is checked in at [`examples/azure-deployment/`](../../examples/azure-deployment/) — customers who prefer to run the deploy themselves can clone the repo and just run `./deploy.sh` (no arguments). The script interactively lists subscriptions → resource groups → regions (same flow as this skill). Use it as a reference when generating project files too.

## Step 0 — preflight checks (run before anything else)

Run these checks at the start of every deployment session. If any fails, **fix it in place and re-run the loop** before continuing to Step 1 — don't skip ahead, and don't ask the user configuration questions you'll have to re-ask after they fix their environment.

```bash
# 1. Azure CLI installed?
az version --query '"azure-cli"' -o tsv
# → If 'az' is not found, stop and install: https://learn.microsoft.com/cli/azure/install-azure-cli

# 2. Signed in?
az account show --query '{name:name, id:id}' -o json
# → On failure, run: az login

# 3. Correct subscription active?
az account show --query name -o tsv
# → If wrong, run: az account set --subscription "<name-or-id>"

# 4. Microsoft.DocumentDB provider registered on the subscription?
az provider show --namespace Microsoft.DocumentDB --query registrationState -o tsv
# → If 'NotRegistered' or 'Unregistered', run:
#     az provider register --namespace Microsoft.DocumentDB
#   Then poll until state is 'Registered' (~1–2 min).

# 5. Caller has Contributor/Owner on the target scope?
az role assignment list --assignee "$(az ad signed-in-user show --query id -o tsv)" \
  --scope "/subscriptions/$(az account show --query id -o tsv)" \
  --query "[].roleDefinitionName" -o tsv
# → Expect Contributor, Owner, or a custom role with Microsoft.DocumentDB/mongoClusters/write.
#   If empty or only a reader role, escalate before proceeding.

# 6. Region supports mongoClusters?
az provider show --namespace Microsoft.DocumentDB \
  --query "resourceTypes[?resourceType=='mongoClusters'].locations[]" -o tsv
# → Confirm the user's chosen location is in the list.
```

`examples/azure-deployment/deploy.sh` and `deploy.ps1` implement checks 1–4 automatically and will `az login` / register the provider / create the resource group as needed. If you're generating deployment files into a user's project, copy those scripts or use them as a template.

## Step 0.5 — is this production or dev/test?

Ask the user **before** anything else in Step 1. The answer drives every default. Never assume.

| If "production" (default) | If "dev / prototype / test" |
|---|---|
| Tier: **M30** (minimum that supports HA) | Tier: **M10** or M20 |
| Storage: **128 GiB** per shard | Storage: **32 GiB** |
| HA: **ZoneRedundantPreferred** | HA: **Disabled** |
| Firewall: Private Endpoint; `allowAzureServices: false` | `allowAzureServices: true` + developer IP rule |
| Password source: **Key Vault reference** | Key Vault preferred; literal OK for throwaway |
| Parameters file: `main.parameters.sample.json` | `main.parameters.dev.json` |

Production is the safer default — the Bicep template and `main.parameters.sample.json` in `examples/azure-deployment/` ship with M30 + ZoneRedundantPreferred + 128 GiB so that a customer who runs `./deploy.sh <rg> <location>` without overrides ends up with a cluster they can actually put workloads on. If the user answers "dev", either:

- pass `--parameters @main.parameters.dev.json` to the deploy script, **or**
- override on the command line:
  ```bash
  az deployment group create \
    --resource-group "<rg>" \
    --template-file main.bicep \
    --parameters computeTier=M10 storageSizeGb=32 haTargetMode=Disabled
  ```

## Step 1 — pick the Azure subscription (always ask, never assume)

The currently active subscription from `az account show` may not be the one the user wants. Always list and confirm — never silently use the active one.

```bash
# Show all subscriptions the signed-in user can access
az account list --query "[].{Name:name, SubscriptionId:id, State:state, IsDefault:isDefault}" \
  --output table
```

Present the list to the user and ask them to pick one (by name or ID). Then set it active so subsequent commands are scoped to it:

```bash
az account set --subscription "<subscription-id-or-name>"
az account show --query "{name:name, id:id}" -o table   # confirm
```

Record the chosen subscription ID as `$SUBSCRIPTION_ID` and pass `--subscription "$SUBSCRIPTION_ID"` to every subsequent `az` command in this flow — this guarantees RG / region lookups stay scoped to the user's choice even if the active context drifts.

If the user has only one subscription, still confirm out loud ("I'll deploy into `<name>` — OK?") rather than silently proceeding.

## Step 2 — pick the resource group in that subscription (existing or new)

List the resource groups **scoped to the chosen subscription** (do not omit `--subscription` — it prevents showing RGs from a different context):

```bash
az group list \
  --subscription "$SUBSCRIPTION_ID" \
  --query "[].{Name:name, Location:location}" \
  --output table
```

Present the list to the user and ask them to pick **one of**:

**(a) Reuse an existing RG** — take its `location` from the table above and use that as the cluster's region by default. **Skip Step 3** (the region is already fixed by the RG). Record it as `$LOCATION`.

**(b) Create a new RG** — ask the user for the new RG name, then continue to Step 3 to pick a region before creating it.

Do not proceed to Step 3 or Step 4 until the user has explicitly picked (a) or (b).

## Step 3 — pick the Azure region (only when creating a new RG)

Reached only when the user chose 2(b). List the regions that support `Microsoft.DocumentDB/mongoClusters` so the user can pick one that is both regionally appropriate and supported:

```bash
az provider show \
  --subscription "$SUBSCRIPTION_ID" \
  --namespace Microsoft.DocumentDB \
  --query "resourceTypes[?resourceType=='mongoClusters'].locations[]" \
  --output tsv
```

Present the list and ask the user to pick one. Record it as `$LOCATION`. Then create the RG in the chosen subscription + region:

```bash
az group create \
  --subscription "$SUBSCRIPTION_ID" \
  --name "<new-rg-name>" \
  --location "$LOCATION"
```

Confirm creation succeeded before moving on:

```bash
az group show --subscription "$SUBSCRIPTION_ID" --name "<new-rg-name>" --query "{name:name, location:location, state:properties.provisioningState}" -o table
```

## Step 4 — gather the remaining cluster inputs

Now that subscription, RG, and location are fixed, ask for cluster-specific values:

| Input | Example | Notes |
|---|---|---|
| Cluster name | `docdb-prod-001` | 8–40 chars, lowercase letters/digits/hyphens; globally unique in Azure |
| Admin username | `clusteradmin` | Avoid reserved names like `admin`, `root` |
| Admin password | — | 8–128 chars; store in Key Vault — **never commit** |
| Compute tier | **M30** (prod default) / `M10`–`M20` (dev) | Full list: `M10`, `M20`, `M30`, `M40`, `M50`, `M60`, `M80`, `M200` |
| Storage per shard (GiB) | **128** (prod default) / `32` (dev) | |
| Shard count | `1` (sufficient up to TB scale — see `documentdb-cluster-sharding`) | |
| High availability | **ZoneRedundantPreferred** (prod default) / `SameZone` / `Disabled` (dev) | Non-Disabled values require M30+ |
| MongoDB server version | `8.0` | |
| Public network access | Default `Enabled` with firewall rules | Or disable and attach Private Endpoint (see `documentdb-security`) |

If the user didn't answer Step 0.5, ask again — without that answer you can't pick the right tier/HA defaults.

## Step 5 — choose a deployment path

| Path | Use when | Section |
|---|---|---|
| **Bicep** (recommended) | Repeatable infra-as-code, PR-reviewed, committed to repo | [Step 6a](#step-6a--deploy-with-bicep) |
| **Azure CLI one-shot** | Prototype, local dev, quick validation | [Step 6b](#step-6b--deploy-with-azure-cli-one-shot) |
| **Terraform** | Existing Terraform estate | [Step 6c](#step-6c--deploy-with-terraform) |
| **Portal** | First-time users who want to see the UI | [Azure portal quickstart](https://learn.microsoft.com/azure/documentdb/quickstart-portal) |

For Bicep, load `references/bicep-cluster-template.md` — it contains the canonical parameterized template and an optional private-endpoint variant.

## Step 6a — deploy with Bicep

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

## Step 6b — deploy with Azure CLI one-shot

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

## Step 6c — deploy with Terraform

Prefer this when the user already uses Terraform. The AzureRM provider 4.x exposes `azurerm_mongo_cluster`, which targets `Microsoft.DocumentDB/mongoClusters` API `2025-09-01`.

Load `references/terraform-cluster-template.md` for the canonical `main.tf` (with variables, validation, sample `terraform.tfvars`, and the firewall-rule pattern via the AzAPI provider). Then:

```bash
export ARM_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
export TF_VAR_admin_password=$(az keyvault secret show \
  --vault-name <kv-name> --name docdb-admin-password --query value -o tsv)

terraform init -upgrade
terraform plan  -out main.tfplan
terraform apply main.tfplan
```

The provider's `high_availability_mode` accepts only `Disabled` and `ZoneRedundantPreferred` (the API also accepts `SameZone`, but that mode is not exposed through `azurerm_mongo_cluster` 4.x — use the Bicep template if you need it). Full Microsoft quickstart: https://learn.microsoft.com/azure/documentdb/quickstart-terraform.

## Step 7 — verify the deployment

```bash
az resource list \
  --resource-group "<resource-group-name>" \
  --namespace Microsoft.DocumentDB \
  --resource-type mongoClusters \
  --query "[].name" \
  --output json
```

Expect one entry matching your cluster name.

## Step 8 — retrieve the connection string

From the portal: **cluster → Connection strings**. The returned string has a `<password>` placeholder you must substitute.

Form of the connection string:

```
mongodb+srv://<user>:<password>@<cluster>.global.mongocluster.cosmos.azure.com/?tls=true&authMechanism=SCRAM-SHA-256&retrywrites=false&maxIdleTimeMS=120000
```

Note `retrywrites=false` — Azure DocumentDB does not support retryable writes; leaving it at the driver default will cause connection errors (see `documentdb-connection` for driver-specific tuning).

## Step 9 — configure access

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

## Step 10 — teardown

```bash
az group delete --name "<resource-group-name>" --yes --no-wait
```

Confirm with the user before running — this removes everything in the resource group, not just the cluster.

## References

- [Quickstart: Deploy an Azure DocumentDB cluster using Bicep](https://learn.microsoft.com/azure/documentdb/quickstart-bicep)
- [Quickstart: Create an Azure DocumentDB cluster by using the Azure portal](https://learn.microsoft.com/azure/documentdb/quickstart-portal)
- [`Microsoft.DocumentDB/mongoClusters` resource reference](https://learn.microsoft.com/azure/templates/microsoft.documentdb/mongoclusters)
- Loaded as needed: `references/bicep-cluster-template.md`, `references/terraform-cluster-template.md`
- Ready-to-run copy (no agent required): [`examples/azure-deployment/`](../../examples/azure-deployment/)

## Related skills

- `documentdb-local-deployment` — Docker / Compose for running DocumentDB locally
- `documentdb-connection` — connection-string tuning after the cluster exists
- `documentdb-security` — Private Endpoint, Entra RBAC, CMK
- `documentdb-cluster-sharding` — M-tier selection, shard-key design at TB scale
- `documentdb-high-availability` — HA, cross-region replica, SLA tiers
- `documentdb-monitoring` — diagnostic settings, slow-query logs
