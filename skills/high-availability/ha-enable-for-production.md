# ha-enable-for-production

**Category:** High Availability & Replication · **Priority:** HIGH

## Why it matters

Enabling **high availability (HA)** on an Azure DocumentDB cluster provisions a standby physical shard for each primary and delivers the **99.99% monthly SLA** with automatic failover and **zero data loss**. The connection string does not change on failover, so applications keep working transparently. In regions that support availability zones, HA shards are placed across zones, adding resilience to datacenter-level failures.

Key guarantees:

- **Synchronous replication** between primary and standby — every write is persisted on both shards before the client gets an ack, so failover is **lossless**. With HA enabled, each shard ends up with **6 data replicas** (3 LRS replicas under the primary + 3 LRS replicas under the standby), all kept in sync.
- **Automatic failover** — the service runs continuous health checks and heartbeats. On primary failure, the standby is promoted and a fresh standby is rebuilt automatically. On standby failure, a new standby is auto-provisioned from the primary. In-flight writes during failover are retried inside the service for continuity.
- **Zone redundancy** — in AZ-enabled regions, the standby is placed in a **different availability zone** from the primary, protecting against datacenter-level events. HA is the **prerequisite** for availability-zone placement; without HA, the cluster runs on locally-redundant storage (LRS) inside a single zone.
- **All regions supported** — HA is available in every Azure region that supports Azure DocumentDB. In regions without AZ support, `ZoneRedundantPreferred` automatically falls back to `SameZone` placement.
- **Single endpoint abstraction** — applications connect through one connection string regardless of how many shards the cluster has; the multi-shard topology is fully transparent to the driver.

Storage integrity is enforced by Azure Storage itself: data is protected with **cyclic redundancy checks (CRCs)**, network traffic is protected with checksums, and any detected corruption is repaired from redundant copies — without operator intervention.

Without HA, each shard relies on LRS — three synchronous Azure Storage replicas inside one zone. Single-replica failures are auto-healed transparently by Azure Storage, but a zone or region failure risks **downtime and possible data loss**.

For non-production clusters where downtime is acceptable, HA can be disabled to cut cost — but assess the risk/cost trade-off explicitly before doing so.

## Incorrect

Running production on a cluster with HA disabled:

```text
Production cluster, HA: off
- No automatic failover on node failure
- No 99.99% SLA coverage
- No zone redundancy (single-zone LRS only)
- Zone/region failure → downtime + possible data loss
```

## Correct

Enable HA on every production and downtime-sensitive cluster:

- Set `highAvailability.targetMode` to `ZoneRedundantPreferred` (API accepts `Disabled`, `SameZone`, `ZoneRedundantPreferred`; the AzureRM Terraform provider currently exposes only `Disabled` and `ZoneRedundantPreferred`).
- Requires `compute.tier` of **M30 or higher**.
- Deploy in a region with availability-zone support so the standby shard lands in a different AZ.
- Keep HA `Disabled` for ephemeral dev/test clusters to save cost; consciously accept the loss of AZ placement and the higher risk profile.

### `targetMode` values

| Value | Behavior |
|---|---|
| `Disabled` | No standby. Single-zone LRS only. No 99.99% SLA, no AZ placement, no automatic failover. Use only for dev/test. |
| `SameZone` | Standby is provisioned in the **same** availability zone as the primary. Survives node failures but not zone outages. |
| `ZoneRedundantPreferred` | **Recommended.** Standby is placed in a different AZ when supported, falling back to `SameZone` in regions without AZ support. Survives node and zone failures and unlocks the 99.99% SLA. |

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
- [Reliability in Azure DocumentDB](https://learn.microsoft.com/azure/reliability/reliability-documentdb) — availability-zone behavior, LRS without HA, synchronous replication guarantee
- [Availability and disaster recovery in Azure DocumentDB — behind the scenes](https://learn.microsoft.com/azure/documentdb/availability-disaster-recovery-under-hood) — cluster anatomy, 6-replica HA layout, CRC + network checksums, single-endpoint abstraction
- [High availability overview](https://learn.microsoft.com/azure/documentdb/high-availability)
- [Scaling and configuring an Azure DocumentDB cluster — enable/disable HA](https://learn.microsoft.com/azure/documentdb/how-to-scale-cluster#enable-or-disable-high-availability)
