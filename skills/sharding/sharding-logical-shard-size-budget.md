# sharding-logical-shard-size-budget

**Category:** Sharding · **Priority:** MEDIUM

## Why it matters

Azure DocumentDB imposes **no hard cap** on the size of a single logical shard, but the official guidance is to keep each logical shard **below 4 TB** for best performance. A logical shard that crosses that threshold is a leading indicator of trouble even before any user-visible symptom shows up.

The 4 TB number isn't a feature limit — it's a performance design point. Past it, operations on that logical shard (compactions, repairs, replica catch-up after a node event) start taking long enough that they bleed into the cluster's normal throughput envelope.

## Why a logical shard gets large

There are only two ways for a single logical shard to grow past 4 TB:

1. **The collection is huge and the shard key has low cardinality.** Each logical shard ends up holding a large slice of a large pie.
2. **The shard key is skewed.** Most logical shards are small, but one or two values dominate and accumulate documents far beyond the average. This is the more common shape in practice and reduces to a hot-partition problem — see [sharding-hot-partition-diagnosis](sharding-hot-partition-diagnosis.md).

Both shapes are *shard-key* problems. Cluster scale-up or scale-out doesn't fix them — a logical shard lives on exactly one physical shard regardless of how big the cluster is.

## Monitoring

Wire alerts so the 4 TB threshold doesn't sneak up on you:

- **Per-logical-shard size** — sample via `db.<collection>.aggregate([{$group: {_id: "$<shardKey>", bytes: {$sum: {$bsonSize: "$$ROOT"}}}}, {$sort: {bytes: -1}}, {$limit: 10}])` on a schedule and emit the top-10 to your metrics pipeline.
- **Top shard-key values by document count** — same query without `$bsonSize`. Fast canary for distribution skew.
- **Per-physical-shard storage utilization** — if one physical shard's storage diverges from its peers, a large logical shard is almost certainly the cause.

Set an alert when any single logical shard crosses **3 TB** (so you have headroom before 4 TB) and another at **4 TB** as a hard signal that resharding planning needs to start.

## What to do as the threshold approaches

When a logical shard is approaching 4 TB, the only durable fix is to **change the shard key so the data redistributes across more, smaller logical shards**. Order of operations:

1. **Identify which shape applies** (low cardinality vs skewed) — see [sharding-hot-partition-diagnosis](sharding-hot-partition-diagnosis.md).
2. **Pick a higher-cardinality or composite key** — see [sharding-shard-key-selection](sharding-shard-key-selection.md).
3. **Reshard during a planned maintenance window** — see [sharding-how-to-commands](sharding-how-to-commands.md).

What you should **not** do:

- **Don't try to "trim" the logical shard** by deleting documents to stay under 4 TB. The underlying skew remains and the shard will refill.
- **Don't add physical shards hoping to "spread out" the large logical shard.** A logical shard is never split across physical shards — adding nodes doesn't help.
- **Don't scale up the cluster tier to absorb a large logical shard.** Per-shard CPU / memory go up for *every* physical shard, costing 4× or more for a problem localized to one logical shard.

## Why the 4 TB number, not 32 TB

The per-physical-shard storage SKU goes up to 32 TB (see `storage/`). The 4 TB number is **per logical shard**, not per physical shard. A healthy physical shard contains hundreds-to-thousands of logical shards summing to whatever the physical-shard SKU allows. Any single logical shard pushing past 4 TB means the distribution is failing — even if the physical shard has headroom.

Think of it this way:

- **Physical-shard storage ceiling (32 TB)** = how big each node can grow.
- **Logical-shard performance budget (4 TB)** = how big any *one* shard-key bucket should be allowed to grow before operations on it start to drag.

## References

- [Sharding — Best practices](https://learn.microsoft.com/azure/documentdb/partitioning#best-practices-for-sharding-data)
- [Logical shards](https://learn.microsoft.com/azure/documentdb/partitioning#logical-shards)
- Related: [sharding-hot-partition-diagnosis](sharding-hot-partition-diagnosis.md), [sharding-shard-key-selection](sharding-shard-key-selection.md), [sharding-logical-vs-physical](sharding-logical-vs-physical.md)
