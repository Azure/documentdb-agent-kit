# Terraform cluster template — Azure DocumentDB

Canonical Terraform configuration for `Microsoft.DocumentDB/mongoClusters`, using the AzureRM provider's `azurerm_mongo_cluster` resource (provider **4.x**, which targets `Microsoft.DocumentDB` API `2025-09-01`). Adapted from the official [Azure DocumentDB Terraform quickstart](https://learn.microsoft.com/azure/documentdb/quickstart-terraform) and the [`azurerm_mongo_cluster` reference](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/mongo_cluster).

> Use this when the user already has a Terraform estate. For greenfield infra-as-code with no prior preference, prefer the Bicep template (`bicep-cluster-template.md`).

## Provider requirements

- Terraform **1.2.0** or later
- AzureRM provider **`~> 4.0`** (4.15+ for full `GeoReplica` support)
- Azure CLI signed in (`az login`); `ARM_SUBSCRIPTION_ID` exported (required by azurerm 4.x)

## `main.tf` — primary cluster

```hcl
terraform {
  required_version = ">= 1.2.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}
}

variable "resource_group_name" {
  type        = string
  description = "Resource group name for the cluster."
}

variable "location" {
  type        = string
  description = "Azure region (must support Microsoft.DocumentDB/mongoClusters)."
  default     = "eastus2"
}

variable "cluster_name" {
  type        = string
  description = "Globally unique cluster name (3–40 chars; lowercase letters, digits, hyphens)."
}

variable "admin_username" {
  type        = string
  description = "Administrator username."
  default     = "clusteradmin"
}

variable "admin_password" {
  type        = string
  description = "Administrator password (8–128 chars). Source from a secret store; never commit."
  sensitive   = true
}

variable "compute_tier" {
  type        = string
  description = "Compute tier. M30+ is required for HA. Use M10/M20 only for dev/test."
  default     = "M30"
  validation {
    condition     = contains(["Free", "M10", "M20", "M25", "M30", "M40", "M50", "M60", "M80", "M200"], var.compute_tier)
    error_message = "compute_tier must be one of Free, M10, M20, M25, M30, M40, M50, M60, M80, M200."
  }
}

variable "storage_size_in_gb" {
  type        = number
  description = "Storage per shard, in GiB."
  default     = 128
}

variable "shard_count" {
  type        = number
  description = "Shard count. Start at 1; sufficient until TB scale."
  default     = 1
}

variable "high_availability_mode" {
  type        = string
  description = "HA mode. ZoneRedundantPreferred requires M30+."
  default     = "ZoneRedundantPreferred"
  validation {
    condition     = contains(["Disabled", "ZoneRedundantPreferred"], var.high_availability_mode)
    error_message = "azurerm_mongo_cluster only accepts Disabled or ZoneRedundantPreferred."
  }
}

variable "mongo_version" {
  type        = string
  description = "MongoDB wire-protocol server version."
  default     = "8.0"
}

variable "allow_azure_services" {
  type        = bool
  description = "Add the documented 0.0.0.0/0.0.0.0 'Allow Azure services' firewall rule."
  default     = true
}

resource "azurerm_resource_group" "cluster" {
  name     = var.resource_group_name
  location = var.location
}

resource "azurerm_mongo_cluster" "cluster" {
  name                   = var.cluster_name
  resource_group_name    = azurerm_resource_group.cluster.name
  location               = azurerm_resource_group.cluster.location
  administrator_username = var.admin_username
  administrator_password = var.admin_password
  compute_tier           = var.compute_tier
  high_availability_mode = var.high_availability_mode
  shard_count            = var.shard_count
  storage_size_in_gb     = var.storage_size_in_gb
  version                = var.mongo_version
}

# "Allow Azure services and resources within Azure to access this cluster"
# is the documented shortcut: start and end both 0.0.0.0. Remove for prod
# Private Endpoint deployments and set publicNetworkAccess via az/REST.
resource "azapi_resource" "allow_azure_services" {
  count     = var.allow_azure_services ? 1 : 0
  type      = "Microsoft.DocumentDB/mongoClusters/firewallRules@2025-09-01"
  name      = "AllowAllAzureServices"
  parent_id = azurerm_mongo_cluster.cluster.id
  body = {
    properties = {
      startIpAddress = "0.0.0.0"
      endIpAddress   = "0.0.0.0"
    }
  }
}

output "cluster_id" {
  value = azurerm_mongo_cluster.cluster.id
}

output "connection_strings" {
  value     = azurerm_mongo_cluster.cluster.connection_strings
  sensitive = true
  description = "List of connection strings. The <user>:<password> placeholders are substituted with the admin credentials when read from state."
}
```

The firewall rule uses the AzAPI provider because `azurerm_mongo_cluster` does not yet expose a first-party child resource for firewall rules. Add it to `required_providers`:

```hcl
terraform {
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.0" }
    azapi   = { source = "Azure/azapi",       version = "~> 2.0" }
  }
}

provider "azapi" {}
```

If you don't need the firewall rule (Private Endpoint–only deployment), drop the `azapi_resource` block and the `azapi` provider.

## `terraform.tfvars` — production sample

```hcl
resource_group_name    = "rg-docdb-prod"
location               = "eastus2"
cluster_name           = "docdb-prod-001"
admin_username         = "clusteradmin"
# admin_password is sensitive — pass via TF_VAR_admin_password env var,
# -var on the CLI, or a Key Vault data source. Never commit a real value.
compute_tier           = "M30"
storage_size_in_gb     = 128
shard_count            = 1
high_availability_mode = "ZoneRedundantPreferred"
mongo_version          = "8.0"
allow_azure_services   = false   # production: use Private Endpoint instead
```

## `terraform.tfvars` — dev sample

```hcl
resource_group_name    = "rg-docdb-dev"
location               = "eastus2"
cluster_name           = "docdb-dev-001"
compute_tier           = "M10"
storage_size_in_gb     = 32
high_availability_mode = "Disabled"
allow_azure_services   = true
```

## Deploy

```bash
# Required for azurerm 4.x
export ARM_SUBSCRIPTION_ID=$(az account show --query id -o tsv)

# Read the password from Key Vault (never commit)
export TF_VAR_admin_password=$(az keyvault secret show \
  --vault-name kv-documentdb --name docdb-admin-password \
  --query value -o tsv)

terraform init -upgrade
terraform plan  -out main.tfplan
terraform apply main.tfplan
```

## Cross-region replica cluster

A replica cluster is a second `azurerm_mongo_cluster` resource with `create_mode = "GeoReplica"` pointing at the primary's resource ID. Most data-plane fields are inherited from the source — only identity, networking, and DR-specific settings need to be set. See `skills/high-availability/ha-cross-region-replica.md` for the full snippet (Bicep + Terraform) and promotion notes.

## Private Endpoint (production)

Set `allow_azure_services = false` and add `azurerm_private_endpoint` + `azurerm_private_dns_zone` resources targeting the cluster ID, with `subresource_names = ["MongoCluster"]`. See `skills/security/SKILL.md` for the full Private DNS zone (`privatelink.mongocluster.cosmos.azure.com`) pattern.

## References

- [Quickstart: Deploy an Azure DocumentDB cluster using Terraform](https://learn.microsoft.com/azure/documentdb/quickstart-terraform)
- [`azurerm_mongo_cluster` resource](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/mongo_cluster)
- [`Microsoft.DocumentDB/mongoClusters` resource reference (Terraform AzAPI)](https://learn.microsoft.com/azure/templates/microsoft.documentdb/mongoclusters)
