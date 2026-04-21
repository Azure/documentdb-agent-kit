# ha-cross-region-replica

**Category:** High Availability & Replication · **Priority:** MEDIUM

## Why it matters

Azure DocumentDB supports **active-passive cross-region replication**: one cluster is the read-write primary, a replica cluster in another region stays read-only and in sync. If a region fails, the replica can be promoted to take writes with minimal interruption. Combined with in-region HA, this delivers the **99.995% SLA** and enables:
- Disaster recovery across regions.
- Read-scale offload to the replica for heavy analytical reads.

## Incorrect

Relying solely on in-region HA for a mission-critical global application:

```text
Single-region cluster, HA: on
- Survives node failure (good)
- Does NOT survive regional outage
- No read-scale offload for distant users
```

## Correct

Pair HA + cross-region replica for production-critical workloads:

1. Enable HA on the primary cluster (see `ha-enable-for-production`).
2. Create a cross-region replica in a paired or geographically near region.
3. Route latency-sensitive reads in that region to the replica (read-only connection string).
4. Document a tested promotion runbook for DR; validate periodically.

```text
Primary:   East US 2  (read-write, HA on)
Replica:   West US 3  (read-only, HA on)
Combined SLA: 99.995%
```

Design for eventual consistency on the replica; writes must still target the primary.

## References

- [HA & cross-region replication best practices](https://learn.microsoft.com/azure/documentdb/high-availability-replication-best-practices)
- [Cross-region replication](https://learn.microsoft.com/azure/documentdb/cross-region-replication)
