# storage-premium-ssdv2-limitations

**Category:** Storage · **Priority:** HIGH

## Why it matters

Premium SSD v2 is the default choice for new Azure DocumentDB clusters, but it has a handful of structural limitations that can block an architecture if discovered late. Surface these *before* picking a storage type, not at the design-review stage.

## Limitations

### 1. Customer-managed keys (CMK) are not supported

Premium SSD v2 clusters use platform-managed encryption only. If your compliance posture mandates CMK / Key Vault–controlled keys, you must use **Premium SSD v1** — set `storage.type = 'PremiumSSD'` at cluster creation. The choice of storage type is fixed at cluster creation and cannot be changed in place (see limitation 3).

### 2. Storage-capacity changes are rate-limited

Storage capacity on Premium SSD v2 disks can be adjusted at most **four times in any 24-hour window**. For newly created clusters, only **three** capacity changes are allowed during the first 24 hours.

Plan capacity moves in one consolidated jump rather than incrementing repeatedly — scripted loops that bump size in small steps will trip the cap quickly.

### 3. No online migration from Premium SSD v1 → v2

The storage-type property is fixed at cluster creation and cannot be flipped in place. The two supported migration paths are:

**Path A — Point-in-time restore (PITR) to a new cluster on v2:**

```azurecli
az documentdb mongo-cluster restore \
  --resource-group "<rg>" \
  --cluster-name "<new-v2-cluster>" \
  --source-cluster "<existing-v1-cluster>" \
  --restore-time "2026-04-29T10:00:00Z"
# In the restore template, set storage.type = 'PremiumSSDv2'.
```

**Path B — Read replica on v2, then promote:**

1. Create a replica cluster of the v1 primary with `storage.type = 'PremiumSSDv2'`.
2. Wait for replication lag to reach ~0 (check **Metrics** on the replica).
3. Promote the replica — see [`high-availability/ha-cross-region-replica`](../high-availability/ha-cross-region-replica.md) for the runbook.
4. Repoint apps to the promoted cluster's connection string (or use the global RW string and let it follow promotion automatically).
5. Decommission the v1 cluster.

### 4. v1 → v2 replication is migration-only

Replication from a Premium SSD v1 source to a Premium SSD v2 target is supported **only for the migration scenarios in limitation 3**. Don't architect for ongoing v1 → v2 replication — v1 can't sustain v2 performance and latency will suffer.

## References

- [Premium SSD v2 disks — Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/high-performance-storage)
- Related: [`storage-disk-hydration-sequencing`](storage-disk-hydration-sequencing.md), [`high-availability/ha-cross-region-replica`](../high-availability/ha-cross-region-replica.md)
