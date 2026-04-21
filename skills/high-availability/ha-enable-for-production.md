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

- Turn on HA in the cluster's Scale / HA blade (or via Bicep/Terraform).
- Deploy in a region with availability-zone support for zone-redundant HA.
- Keep HA off for ephemeral dev/test clusters to save cost.

```bicep
// Bicep sketch (check the current resource schema for exact property names)
resource ddb 'Microsoft.DocumentDB/...@...' = {
  name: clusterName
  properties: {
    highAvailability: {
      enabled: true
    }
    // ...
  }
}
```

## References

- [HA & cross-region replication best practices](https://learn.microsoft.com/azure/documentdb/high-availability-replication-best-practices)
- [High availability overview](https://learn.microsoft.com/azure/documentdb/high-availability)
