# storage-choose-premium-ssdv2

**Category:** Storage · **Priority:** HIGH

## Why it matters

On Azure DocumentDB, **Premium SSD v2** decouples IOPS and bandwidth from disk capacity — the maximum throughput for your cluster depends on the **compute tier**, not how much storage you provisioned. The same 1 TB disk that capped at 5,000 IOPS on Premium SSD v1 can sustain 20,000 IOPS on Premium SSD v2 (or up to 80,000 IOPS on the largest tier), at no added cost. For any new I/O-intensive workload, Premium SSD v2 should be the default.

The one structural reason to stay on Premium SSD v1: **customer-managed keys (CMK) are not supported on Premium SSD v2.** If your compliance posture mandates CMK, you must use Premium SSD v1.

## Incorrect

Provisioning Premium SSD v1 with an oversized disk to "buy" IOPS:

```bicep
// Anti-pattern — paying for 20 TB to unlock IOPS the workload needs.
storage: {
  sizeGb: 20000           // only ~800 GB of data
  type: 'PremiumSSD'      // v1
}
compute: {
  tier: 'M50'
}
```

Picking Premium SSD v1 by default on a new cluster without a CMK requirement:

```bicep
storage: {
  sizeGb: 256
  type: 'PremiumSSD'      // leaves up to 12× headroom on the floor
}
```

## Correct

Premium SSD v2 — size storage for data, size compute for throughput:

```bicep
resource cluster 'Microsoft.DocumentDB/mongoClusters@2025-09-01' = {
  name: clusterName
  location: location
  properties: {
    administrator: {
      userName: adminUsername
      password: adminPassword
    }
    serverVersion: '8.0'
    storage: {
      sizeGb: 256
      type: 'PremiumSSDv2'   // IOPS/bandwidth ceiling is determined by `compute.tier`
    }
    compute: {
      tier: 'M50'            // → 12,800 IOPS / 290 MBps auto-applied
    }
    sharding: {
      shardCount: 1
    }
    highAvailability: {
      targetMode: 'ZoneRedundantPreferred'
    }
  }
}
```

Terraform equivalent:

```terraform
resource "azurerm_mongo_cluster" "cluster" {
  name                   = var.cluster_name
  resource_group_name    = data.azurerm_resource_group.existing.name
  location               = var.location
  administrator_username = var.admin_username
  administrator_password = var.admin_password
  shard_count            = 1
  compute_tier           = "M50"
  high_availability_mode = "ZoneRedundantPreferred"
  storage_size_in_gb     = 256
  storage_type           = "PremiumSSDv2"
  version                = "8.0"
}
```

## Decision matrix

| Requirement | Pick |
|---|---|
| New production cluster, no CMK mandate | **Premium SSD v2** |
| I/O-intensive workload (≥ 20k IOPS, ≥ 300 MBps) | **Premium SSD v2** (only path above v1's 20k IOPS ceiling) |
| Customer-managed keys (CMK) required | Premium SSD v1 |
| Migrating from an existing Premium SSD v1 cluster | Premium SSD v2 via PITR or read-replica promotion — see [storage-premium-ssdv2-limitations](storage-premium-ssdv2-limitations.md) |

## References

- [Premium SSD v2 disks — Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/high-performance-storage)
