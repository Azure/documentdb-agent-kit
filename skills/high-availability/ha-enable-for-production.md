# ha-enable-for-production

**Category:** High Availability & Replication · **Priority:** HIGH

## Why it matters

Enabling **high availability (HA)** on an Azure DocumentDB cluster provisions a standby physical shard for each primary and delivers the **99.99% monthly SLA** with automatic failover and **zero data loss**. The connection string does not change on failover, so applications keep working transparently. In regions that support availability zones, HA shards are placed across zones, adding resilience to datacenter-level failures.

For non-production clusters where downtime is acceptable, HA can be disabled to cut cost.

## Incorrect

Running production on a cluster with HA disabled:

```text
Production cluster, HA: off
- No automatic failover on node failure
- No 99.99% SLA coverage
- Downtime requires manual intervention
```

## Correct

Enable HA on every production and downtime-sensitive cluster:

- Set `highAvailability.targetMode` to `ZoneRedundantPreferred` (API accepts `Disabled`, `SameZone`, `ZoneRedundantPreferred`; the AzureRM Terraform provider currently exposes only `Disabled` and `ZoneRedundantPreferred`).
- Requires `compute.tier` of **M30 or higher**.
- Deploy in a region with availability-zone support so the standby shard lands in a different AZ.
- Keep HA `Disabled` for ephemeral dev/test clusters to save cost.

### Bicep (full template: `skills/azure-deployment/references/bicep-cluster-template.md`)

```bicep
resource cluster 'Microsoft.DocumentDB/mongoClusters@2025-09-01' = {
  name: clusterName
  location: location
  properties: {
    administrator: { userName: adminUsername, password: adminPassword }
    serverVersion: '8.0'
    sharding:      { shardCount: 1 }
    storage:       { sizeGb: 128 }
    compute:       { tier: 'M30' }              // M30+ required for HA
    highAvailability: {
      targetMode: 'ZoneRedundantPreferred'      // 99.99% SLA, zero data loss
    }
  }
}
```

### Terraform (full template: `skills/azure-deployment/references/terraform-cluster-template.md`)

```hcl
resource "azurerm_mongo_cluster" "primary" {
  name                   = var.cluster_name
  resource_group_name    = azurerm_resource_group.rg.name
  location               = azurerm_resource_group.rg.location
  administrator_username = var.admin_username
  administrator_password = var.admin_password
  compute_tier           = "M30"
  high_availability_mode = "ZoneRedundantPreferred"   # 99.99% SLA
  shard_count            = 1
  storage_size_in_gb     = 128
  version                = "8.0"
}
```

### Toggling HA on an existing cluster

```bash
az rest --method PATCH \
  --url "https://management.azure.com/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.DocumentDB/mongoClusters/<cluster>?api-version=2025-09-01" \
  --body '{"location":"<region>","properties":{"highAvailability":{"targetMode":"ZoneRedundantPreferred"}}}'
```

## References

- [HA & cross-region replication best practices](https://learn.microsoft.com/azure/documentdb/high-availability-replication-best-practices)
- [High availability overview](https://learn.microsoft.com/azure/documentdb/high-availability)
- [Scaling and configuring an Azure DocumentDB cluster — enable/disable HA](https://learn.microsoft.com/azure/documentdb/how-to-scale-cluster#enable-or-disable-high-availability)
