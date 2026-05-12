# storage-disk-hydration-sequencing

**Category:** Storage · **Priority:** MEDIUM

## Why it matters

After certain operations on a Premium SSD v2 cluster — creation, point-in-time-restore, storage scale-out, replica promotion — the underlying disk goes through a **hydration** phase. While the disk is hydrating, **no other operation that touches the disk is allowed**, and attempts will fail with:

> Unable to complete the operation because the disk is still being hydrated. Retry after some time.

This includes **service-triggered failovers**, so an HA failover that fires during hydration won't proceed normally. Sequencing scale and HA operations correctly is therefore a reliability concern, not just an operational nicety.

## Operations that can trigger the hydration error

- Compute scaling (changing `compute.tier`) immediately after a previous scale.
- Storage scaling (changing `storage.sizeGb`).
- Enabling **high availability** (`highAvailability.targetMode`) shortly after another change.
- Using **PITR** to create a new cluster and immediately enabling HA.
- Service-triggered failovers while the disk is mid-hydration.

## Incorrect

Stacking changes back-to-back on a freshly created or restored cluster:

```azurecli
# t+0  Cluster created on Premium SSD v2
az deployment group create --template-file cluster.bicep ...

# t+1m  Scale compute
az resource update --set properties.compute.tier="M60" ...

# t+2m  Bump storage
az resource update --set properties.storage.sizeGb=1024 ...

# t+3m  Enable HA   ← likely to fail with "disk is still being hydrated"
az resource update --set properties.highAvailability.targetMode="ZoneRedundantPreferred" ...
```

PITR + enable HA in one shot:

```bicep
// Anti-pattern — restoring a new cluster AND requesting HA in the same template
// while the restored disk is still hydrating.
resource restored 'Microsoft.DocumentDB/mongoClusters@2025-09-01' = {
  properties: {
    createMode: 'PointInTimeRestore'
    restoreParameters: { /* … */ }
    highAvailability: { targetMode: 'ZoneRedundantPreferred' }  // ← will likely error
  }
}
```

## Correct

**Space out operations** and verify each completes before triggering the next. A safe pattern:

```bash
# Step 1: create / restore the cluster — wait for it to be Ready.
az deployment group create --template-file cluster.bicep ...
az resource show \
  --resource-group "<rg>" --name "<cluster>" \
  --resource-type Microsoft.DocumentDB/mongoClusters \
  --query "properties.provisioningState" -o tsv   # → Succeeded

# Step 2: give the disk time to finish hydrating (workload-dependent;
#         a few minutes for small clusters, longer for multi-TB).
#         Optional sanity check: run a small workload and watch latency settle.

# Step 3: enable HA on its own.
az resource update \
  --resource-group "<rg>" --name "<cluster>" \
  --resource-type Microsoft.DocumentDB/mongoClusters \
  --set properties.highAvailability.targetMode="ZoneRedundantPreferred"
az resource show \
  --resource-group "<rg>" --name "<cluster>" \
  --resource-type Microsoft.DocumentDB/mongoClusters \
  --query "properties.provisioningState" -o tsv   # → Succeeded

# Step 4: only now scale compute or storage if needed.
az resource update \
  --resource-group "<rg>" --name "<cluster>" \
  --resource-type Microsoft.DocumentDB/mongoClusters \
  --set properties.compute.tier="M60"
```

### Multi-step IaC: prefer sequential deployments

Split a "create cluster + enable HA + grow storage" template into two or three deployments, with a wait between them, instead of one mega-template. The provisioning service serializes operations on a single resource, but it does **not** wait for hydration between them, which is the source of the error.

### Watch for HA-triggered hydration during failovers

Service-triggered HA failovers can themselves leave the new primary in a hydrating state for a short window. Avoid scheduling planned compute/storage scaling immediately after a known failover — wait for cluster metrics to stabilize first.

### If you do hit the error

Just retry the operation after a short backoff. Hydration is bounded; the error is transient. Idempotent retry with exponential backoff is the right pattern in automation.

## References

- [Premium SSD v2 disks — Azure DocumentDB: limitations](https://learn.microsoft.com/azure/documentdb/high-performance-storage#current-limitations-of-high-performance-storage-premium-ssd-v2-storage)
- Related: [`high-availability/ha-enable-for-production`](../high-availability/ha-enable-for-production.md)
