---
name: documentdb-high-availability
description: High availability, business-continuity, and disaster-recovery best practices for Azure DocumentDB — enabling in-region HA with availability zones (99.99% SLA), adding active-passive cross-region replica clusters (99.995% SLA), and understanding automatic backup retention. Use when designing production topology, planning failover, provisioning DR, picking regions, or reviewing cluster architecture.
license: MIT
---

# High Availability, Replication & DR — Azure DocumentDB

Azure DocumentDB's resiliency model has three layers. Pick the right combination for the workload — production-critical workloads should use all three.

| Layer | What it protects against | SLA contribution | Automatic? |
|---|---|---|---|
| **In-region HA** (standby shard per primary, synchronous replication) | Node / zone failures within a region | 99.99% | ✅ Failover is automatic; connection string is unchanged |
| **Cross-region replica** (active-passive, asynchronous) | Regional outage; provides read scale-out | + 0.005% → **99.995%** combined | ❌ Promotion is **customer-triggered** (shared-responsibility DR); HA must be re-enabled on the promoted cluster |
| **Automatic backups** (35 d active / 7 d deleted clusters) | Accidental deletion or corruption | — | ✅ Continuous, no perf impact |

## Replication model at a glance

- **Primary ↔ standby shard (in-region):** synchronous — every write commits to both before the client gets an ack, so failover is **lossless** and reads on the standby (after promotion) are strongly consistent. With HA on, each shard has **6 replicas** in total: 3 LRS replicas under the primary shard + 3 LRS replicas under the standby shard. In AZ-enabled regions the primary and standby sit in **different availability zones**.
- **Primary cluster ↔ cross-region replica:** asynchronous — design for eventual consistency on the replica. Some writes acknowledged on the primary **may not yet** be on the replica, so regional promotion has a **non-zero RPO** (recent writes can be lost). Replication lag scales with the primary's write intensity and the load on both clusters.
- **Without HA:** each shard uses locally-redundant storage (LRS) with 3 synchronous Azure Storage replicas. Single-replica failures are auto-healed by Azure Storage (CRC checks + network checksums protect against silent corruption), but a **zone or region failure can cause downtime and possible data loss**. HA is also a prerequisite for availability-zone placement.

> Applications connect to a cluster through a **single connection string and endpoint** regardless of shard count. The multi-shard topology is fully abstracted — a 16-shard cluster looks like one MongoDB endpoint to the driver.

## Feature comparison

How HA and cross-region replicas protect different failure modes:

| Failure scenario | Feature | No data loss (RPO = 0) | Survives region-wide outage | Automatic failover | Connection string preserved |
|---|---|:---:|:---:|:---:|:---:|
| Physical shard / zone failure | In-region HA | ✅ (synchronous) | ❌ | ✅ | ✅ |
| Regional outage | Cross-region replica | ❌ (asynchronous; RPO > 0) | ✅ | ❌ (customer-triggered) | ✅ ¹ |

¹ Only when the application uses the **Global read-write** connection string (`<cluster>.global.mongocluster.cosmos.azure.com`). The cluster-specific / "self" connection string becomes read-only after promotion.

## Best-practice decision matrix

| Scenario | Recommendation |
|---|---|
| Production cluster | Enable HA |
| Need 99.99% SLA | Enable HA |
| Need 99.995% SLA | Enable HA **and** create a cross-region replica |
| Automatic failover from node/zone failure | Enable HA |
| Cross-region disaster recovery | Create a replica cluster |
| Read scale-out within a single region (analytics / reporting offload) | Create a **same-region** replica (no DR benefit; you can have only one replica per primary, so this trades cross-region DR for in-region read offload) |
| Read scale-out across regions | Create a replica cluster |
| Availability-zone placement required | Enable HA (HA is required for AZ support) |
| Non-production / dev-test cluster | Disable HA to reduce cost |
| Recover from accidental delete/modify | Automatic backups (35-day retention for active clusters) |

## Rules

- [ha-enable-for-production](ha-enable-for-production.md) — Enable HA on all production clusters for the 99.99% SLA, automatic failover, zone redundancy, and zero-data-loss synchronous replication.
- [ha-cross-region-replica](ha-cross-region-replica.md) — Add an active-passive replica (cross-region for DR + read scale-out, same-region for pure read scale-out); HA + cross-region replica = 99.995% SLA. Includes the post-promotion runbook (re-enable HA, update connection strings, restore the replica).
- [ha-backup-retention](ha-backup-retention.md) — Automatic backups are taken continuously and retained for **35 days** on active clusters and **7 days** on deleted clusters. Use them to recover from accidental deletes or modifications.

## References

- [Best practices for HA and cross-region replication in Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/high-availability-replication-best-practices)
- [Reliability in Azure DocumentDB](https://learn.microsoft.com/azure/reliability/reliability-documentdb)
- [Availability and disaster recovery in Azure DocumentDB — behind the scenes](https://learn.microsoft.com/azure/documentdb/availability-disaster-recovery-under-hood) — cluster anatomy, 6-replica HA layout, replication-lag drivers
