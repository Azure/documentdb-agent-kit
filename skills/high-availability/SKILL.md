---
name: documentdb-high-availability
description: High availability and disaster-recovery best practices for Azure DocumentDB — enabling in-region HA (99.99% SLA) and adding active-passive cross-region replica clusters (99.995% SLA). Use when designing production topology, planning failover, provisioning DR, or reviewing cluster architecture.
license: MIT
---

# High Availability & Replication — Azure DocumentDB

Azure DocumentDB's HA model uses in-region standby physical shards and active-passive cross-region replica clusters. Documented SLAs:

- **99.99%** — HA enabled
- **99.995%** — HA + cross-region replica

## Rules

- [ha-enable-for-production](ha-enable-for-production.md) — Enable HA on all production clusters for the 99.99% SLA and automatic failover.
- [ha-cross-region-replica](ha-cross-region-replica.md) — Add an active-passive cross-region replica for DR and read scale-out; HA + replica = 99.995% SLA.
