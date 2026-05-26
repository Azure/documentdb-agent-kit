---
name: documentdb-storage
description: Storage configuration guidance for Azure DocumentDB — when and how to use Premium SSD v2 high-performance storage, IOPS/bandwidth caps that are gated by compute tier (not disk size), Premium SSD v2 limitations (no CMK, migration paths, disk-hydration sequencing), and storage capacity change limits. Use when picking a storage type at cluster creation, sizing for I/O-intensive workloads, migrating from Premium SSD to Premium SSD v2, or sequencing compute/storage/HA changes on a Premium SSD v2 cluster.
license: MIT
---

# Storage — Azure DocumentDB

Azure DocumentDB clusters use **remote premium SSD storage**. Two disk types are offered:

| Storage type | IOPS / bandwidth scaling | Max IOPS | CMK | Use it for |
|---|---|---|---|---|
| **Premium SSD** (v1) | Scales with **disk capacity** — bigger disk → higher IOPS | 20,000 | ✔️ | Legacy clusters, scenarios that require CMK |
| **Premium SSD v2** | **Decoupled** from disk size — IOPS/bandwidth gated by **compute tier** | 80,000 | ❌ | New production clusters; any I/O-intensive workload |

**Premium SSD v2 is the default recommendation for new clusters.** It delivers up to a **12× performance boost at no added cost** by removing the disk-size lever from the IOPS equation — you size storage for *capacity* and size compute for *throughput*, independently.

## How Premium SSD v2 changes sizing

On Premium SSD v1, hitting 20,000 IOPS required provisioning a 20 TB disk even when only ~1 TB of data was stored. On Premium SSD v2, the **highest achievable IOPS and bandwidth for the chosen compute tier are auto-configured** regardless of disk size:

- Choose storage size based on **how much data** the cluster will hold.
- Choose compute tier based on **how much IOPS / MBps** the workload needs (see [storage-tier-iops-caps](storage-tier-iops-caps.md)).
- No knobs to tune — the upper-bound IOPS/bandwidth for the tier are applied automatically at no extra cost.

## Rules

- [storage-choose-premium-ssdv2](storage-choose-premium-ssdv2.md) — When to pick Premium SSD v2 vs Premium SSD; the CMK trade-off.
- [storage-tier-iops-caps](storage-tier-iops-caps.md) — Compute-tier → max IOPS / MBps table; size compute for throughput, not disk for IOPS.
- [storage-premium-ssdv2-limitations](storage-premium-ssdv2-limitations.md) — Known limits: no CMK, capacity-change cap, replication restrictions, no online v1→v2 migration.
- [storage-disk-hydration-sequencing](storage-disk-hydration-sequencing.md) — Space out compute scale / storage scale / HA-enable operations while the disk is hydrating.

## References

- [Premium SSD v2 disks — Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/high-performance-storage)
