---
name: documentdb-sharding
description: Horizontal sharding (partitioning) for Azure DocumentDB collections — when to shard vs stay single-shard, how to pick a shard key for read-heavy vs write-heavy workloads, the logical/physical shard mental model, scaling out vs scaling up, hot-partition diagnosis, and the `sh.shardCollection` / `sh.reshardCollection` commands. Use when deciding whether to shard a collection, choosing or changing a shard key, sizing a cluster, or troubleshooting uneven storage / throughput across physical shards.
license: MIT
---

# Sharding — Azure DocumentDB

Azure DocumentDB shards collections **horizontally** by hashing a shard key from each document and bucketing documents into **logical shards**, which the service then maps onto **physical shards** (the actual nodes that store data and serve traffic). The service hides the placement: you pick a shard key, the service handles the hash range and rebalancing.

The decisions that *you* own:

1. **Whether to shard at all.** Sharding is not the default and is not always the right answer — single-shard clusters scale up vertically and avoid the cross-shard tax.
2. **What to shard on.** The shard key is the single biggest determinant of long-term performance. It can be changed later (`sh.reshardCollection`), but only at significant cost once the collection is large.
3. **How big each physical shard should be.** The cluster tier and storage SKU set the CPU / memory / IOPS budget per physical shard, and that's what your shard key needs to fit inside.

## Rules

- [sharding-when-to-shard](sharding-when-to-shard.md) — Default to single-shard. Shard only when a collection's storage or transaction volume can exceed one physical shard's budget (e.g., > 32 TB on the largest storage SKU). Sharded and unsharded collections can coexist.
- [sharding-shard-key-selection](sharding-shard-key-selection.md) — Read-heavy → pick the most frequent query filter to localize to one physical shard. Write-heavy → pick the highest-cardinality, evenly-distributed field. Avoid hot keys (monotonic IDs, timestamps, tenant IDs with skew).
- [sharding-logical-vs-physical](sharding-logical-vs-physical.md) — Mental model: logical shards are unbounded in count and size; physical shards are bounded by the cluster's compute/storage budget. Multiple logical shards map to one physical shard, never the reverse. Cross-shard transactions are supported but not free.
- [sharding-scaling-out-vs-up](sharding-scaling-out-vs-up.md) — Scale up (bigger tier / storage SKU) grows per-shard capacity without rebalancing; scale out (more physical shards) rebalances logical shards across the new layout. Read-heavy benefits from a bigger tier; write-heavy benefits from more shards or a bigger storage SKU.
- [sharding-hot-partition-diagnosis](sharding-hot-partition-diagnosis.md) — Symptoms (uneven CPU / IOPS / storage across shards) and remediation: reshard, change the key, or add a secondary high-cardinality field.
- [sharding-how-to-commands](sharding-how-to-commands.md) — `sh.shardCollection` / `db.adminCommand({ shardCollection: "db.collection", key: {...} })`, `sh.reshardCollection`, and the requirement to create an explicit index on the shard key (with `enableLargeIndexKeys: true`).
- [sharding-logical-shard-size-budget](sharding-logical-shard-size-budget.md) — Keep individual logical shards **below 4 TB** for best performance, even though the service imposes no hard cap.

## Quick decision flow

```
collection's expected size or throughput ≤ one physical shard's budget?
  ├─ yes → leave unsharded. Scale up if needed.
  └─ no  → shard.
            ├─ read-heavy?  → key = most frequent query filter
            └─ write-heavy? → key = highest-cardinality, evenly distributed field
```

## References

- [Sharding for horizontal scalability in Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/partitioning)
- [Compute and storage in Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/compute-storage)
- Related: `indexing/` (index on the shard key), `query-optimization/` (single-shard vs scatter-gather queries), `high-availability/` (replica sets within each physical shard)
