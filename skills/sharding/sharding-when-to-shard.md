# sharding-when-to-shard

**Category:** Sharding · **Priority:** HIGH

## Why it matters

Sharding is **not the default** in Azure DocumentDB, and choosing to shard when you don't need to imposes real costs: a shard key constraint on every document, a hash-range placement that may bias queries toward scatter-gather, and the operational overhead of monitoring uneven distribution across physical shards. Single-shard clusters scale up vertically (bigger tier, bigger storage SKU) and avoid all of that.

The right question is not *"should this collection be sharded?"* It's *"will this collection's storage or transaction volume exceed what one physical shard can deliver?"* If the answer is no, leave it unsharded.

## The rule

Shard a collection **only when** at least one of the following is true for the foreseeable lifetime of the workload:

1. **Storage exceeds one physical shard's disk budget.** The largest available storage SKU offers up to **32 TB per shard** — a collection that will fit comfortably under that ceiling, with growth headroom, does not need to be sharded.
2. **Transaction volume saturates one physical shard's compute / IOPS budget.** A single physical shard's CPU, memory, and IOPS are bounded by the cluster tier and storage SKU. If a workload's peak QPS or write IOPS demonstrably exceeds what the largest single-shard configuration can deliver, sharding distributes the load.
3. **You need a per-shard isolation property** that single-shard cannot provide (rare — usually multi-tenant fairness use cases).

If none of those is true, **keep the collection unsharded** and scale up the cluster tier or storage SKU as needed.

## Sharded and unsharded can coexist

A multi-shard cluster does not force every collection to be sharded. **Sharded and unsharded collections live happily side by side in the same cluster**, and the service distributes unsharded collections across the physical shards to keep utilization balanced. So the decision is per-collection, not per-cluster.

This matters for typical workloads where one or two large collections need horizontal scale but the rest of the schema (lookup tables, config, audit logs) is small and best left alone.

## Incorrect

```text
☐ Sharding every collection because the cluster has multiple physical shards.
  → Unsharded collections are distributed automatically. Don't shard small collections
    just because they share a cluster with a large one.

☐ Sharding a 50 GB collection "for future-proofing."
  → The shard-key constraint is permanent; reshard is expensive. Scale up first.

☐ Sharding to "spread read load across nodes" when the working set fits in one shard.
  → Reads against a single physical shard already use the full tier's CPU / memory.
    Sharding adds scatter-gather risk without solving a real bottleneck.

☐ Sharding because a benchmark spiked once.
  → Identify the real, sustained ceiling first - tier scale-up, indexing improvements,
    or query rewrites may close the gap without sharding.
```

## Correct

### 1. Capacity-check the unsharded option first

Before sharding, confirm a properly-sized **single-shard** cluster cannot meet requirements:

- Project peak storage at the workload's 12–24 month horizon. Compare against the largest available storage SKU (currently up to 32 TB per shard). If the projection fits with headroom, stay single-shard.
- Run the workload (or a representative load test) against the largest tier you'd consider. Measure sustained CPU, memory, IOPS, and request latency. If headroom remains, stay single-shard.
- Confirm indexing is correct (see `indexing/`) and queries are not doing accidental collection scans (see `query-optimization/`). These problems look like "we need to shard" but aren't.

### 2. Shard the right collections, not all of them

If one or two collections cross the single-shard ceiling, shard *only those*. Leave the rest unsharded. The service balances unsharded collections automatically across physical shards.

### 3. Plan the shard key before sharding

Once you've decided to shard, the shard-key decision is the next critical step — see [sharding-shard-key-selection](sharding-shard-key-selection.md). Don't run `sh.shardCollection` against production until you have:

- A documented read/write mix
- A field (or composite) that distributes evenly **and** aligns with the most common query filter (for read-heavy) or has the highest cardinality (for write-heavy)
- An index on the chosen shard-key field

## References

- [Sharding for horizontal scalability in Azure DocumentDB — Best practices](https://learn.microsoft.com/azure/documentdb/partitioning#best-practices-for-sharding-data)
- [Compute and storage in Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/compute-storage)
- Related: [sharding-shard-key-selection](sharding-shard-key-selection.md), [sharding-scaling-out-vs-up](sharding-scaling-out-vs-up.md)
