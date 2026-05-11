---
name: documentdb-high-availability
description: High availability, business-continuity, and disaster-recovery best practices for Azure DocumentDB — enabling in-region HA with availability zones (99.99% SLA), adding active-passive cross-region replica clusters (99.995% SLA), and understanding automatic backup retention. Use when designing production topology, planning failover, provisioning DR, picking regions, or reviewing cluster architecture.
license: MIT
---

# High Availability, Replication & DR — Azure DocumentDB

Azure DocumentDB's resiliency model has three layers. Pick the right combination for the workload — production-critical workloads should use all three.

| Layer | What it protects against | SLA contribution | Automatic? |
|---|---|---|---|
| **In-region HA** (standby shard per primary, synchronous replication) | Node / zone failures within a region | 99.99 % | ✅ Failover is automatic; connection string is unchanged |
| **Cross-region replica** (active-passive, asynchronous) | Regional outage; provides read scale-out | + 0.005 % → **99.995 %** combined | ❌ Promotion is **customer-triggered** (shared-responsibility DR); HA must be re-enabled on the promoted cluster |
| **Automatic backups** (35 d active / 7 d deleted clusters) | Accidental deletion or corruption | — | ✅ Continuous, no perf impact |

## Replication model at a glance

- **Primary ↔ standby shard (in-region):** synchronous — zero data loss on automatic failover.
- **Primary cluster ↔ cross-region replica:** asynchronous — design for eventual consistency on the replica; writes still go to the primary until you explicitly promote the replica.
- **Without HA:** each shard uses locally-redundant storage (LRS) with 3 synchronous Azure Storage replicas. Single-replica failures are auto-healed by Azure Storage, but a **zone or region failure can cause downtime and possible data loss**. HA is also a prerequisite for availability-zone placement.

## Best-practice decision matrix

| Scenario | Recommendation |
|---|---|
| Production cluster | Enable HA |
| Need 99.99 % SLA | Enable HA |
| Need 99.995 % SLA | Enable HA **and** create a cross-region replica |
| Automatic failover from node/zone failure | Enable HA |
| Cross-region disaster recovery | Create a replica cluster |
| Read scale-out within a single region (analytics / reporting offload) | Create a **same-region** replica (no DR benefit) |
| Read scale-out across regions | Create a replica cluster |
| Availability-zone placement required | Enable HA (HA is required for AZ support) |
| Non-production / dev-test cluster | Disable HA to reduce cost |
| Recover from accidental delete/modify | Automatic backups (35-day retention for active clusters) |

## Rules

- [ha-enable-for-production](ha-enable-for-production.md) — Enable HA on all production clusters for the 99.99 % SLA, automatic failover, zone redundancy, and zero-data-loss synchronous replication.
- [ha-cross-region-replica](ha-cross-region-replica.md) — Add an active-passive replica (cross-region for DR + read scale-out, same-region for pure read scale-out); HA + cross-region replica = 99.995 % SLA. Includes the post-promotion runbook (re-enable HA, update connection strings, restore the replica).
- [ha-backup-retention](ha-backup-retention.md) — Automatic backups are taken continuously and retained for **35 days** on active clusters and **7 days** on deleted clusters. Use them to recover from accidental deletes or modifications.

## References

- [Best practices for HA and cross-region replication in Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/high-availability-replication-best-practices)
- [Reliability in Azure DocumentDB](https://learn.microsoft.com/azure/reliability/reliability-documentdb)
