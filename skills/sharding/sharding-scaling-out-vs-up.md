# sharding-scaling-out-vs-up

**Category:** Sharding · **Priority:** MEDIUM

## Why it matters

Azure DocumentDB clusters scale in two distinct ways and they solve different problems. Choosing wrong wastes money or, worse, fails to fix the bottleneck.

| Knob | What it changes | Triggers rebalancing? | Best for |
|---|---|---|---|
| **Scale up** — change cluster tier or storage SKU | Per-physical-shard capacity (CPU, memory, IOPS, disk size) | **No** — physical shard count is unchanged; logical shards stay in place | Read-heavy workloads, working sets that don't fit in RAM, IOPS-limited writes, growing storage on a non-sharded cluster |
| **Scale out** — add physical shards | Total cluster capacity (more shards × same per-shard size) | **Yes** — hash range is redistributed and logical shards rebalance across the new layout | Write-heavy workloads, total storage outgrowing what one shard SKU can hold, per-shard CPU saturated even at the largest tier |

The two knobs are complementary, not alternatives. Production clusters typically use both: scale up to the right per-shard size, then scale out only when one shard's budget isn't enough.

## Scale up: bigger shards, same number

Changing the **cluster tier** changes the CPU and memory of each physical shard. Changing the **storage SKU** changes the disk size and IOPS of each physical shard. After a scale-up operation:

- The number of physical shards is the same.
- The placement of logical shards on physical shards is **unchanged** — no rebalance, no data movement.
- All physical shards in the cluster have the new, identical capacity.

This is the cheap, fast knob. Use it first.

### When scale up is the right answer

- The workload is **read-heavy** and the bottleneck is per-shard CPU or memory (e.g., working set doesn't fit in cache).
- Storage is growing but stays comfortably under the per-shard ceiling (currently up to 32 TB on the largest SKU).
- Write IOPS is the bottleneck and you haven't yet moved to the largest storage SKU.
- The cluster is **single-shard** today and you want to defer sharding — scale up until you actually exceed one shard's budget.

### When scale up isn't enough

- You're already on the largest tier **and** largest storage SKU, and per-shard CPU / IOPS / disk is still saturated.
- Total storage projection exceeds what one shard can hold even at the largest SKU.
- You need *more parallelism* than a single shard can deliver no matter how large.

At that point, scale out.

## Scale out: more shards, same per-shard size

Adding physical shards expands the cluster's hash range to cover new nodes. The service:

1. Recomputes the hash-range mapping so each physical shard owns an evenly-sized slice.
2. **Rebalances logical shards** across the new layout — some logical shards move to the new physical shards.
3. Updates the routing so subsequent queries hit the new mapping.

This is the more disruptive knob — there's a data-movement window during rebalancing. Plan for it.

### When scale out is the right answer

- **Write-heavy** workloads where total write throughput exceeds what one physical shard can sustain even at the largest tier + SKU.
- Total storage that exceeds one physical shard's disk ceiling — sharding *is* the only way past the per-shard storage limit.
- Per-shard CPU saturation that scale-up has already failed to fix.

### When scale out is the wrong answer

- The workload is **read-heavy** with the working set fitting comfortably in one shard's memory — scale up the tier instead, you get cache reuse you'd lose by spreading across shards.
- One **hot logical shard** is the bottleneck — adding more physical shards doesn't help because that logical shard still lives on exactly one of them. Fix the shard key first (see [sharding-hot-partition-diagnosis](sharding-hot-partition-diagnosis.md)).
- Queries don't include the shard key — adding physical shards makes scatter-gather queries **more expensive**, not less, because the fan-out is wider.

## All physical shards are identical

A subtle but important property: in a multi-shard cluster, **every physical shard has the same capacity**. You cannot have a cluster with two large shards and one small shard, or a cluster where one shard runs a different storage SKU than the others. Scale up changes the tier or SKU for **all** physical shards at once.

This simplifies reasoning — capacity is `shard_count × per_shard_capacity` — but it also means scale up costs scale linearly with shard count. A 4-shard cluster at the next tier up costs ~4× the per-shard upgrade.

## Reads vs writes: the heuristic

| Workload | First knob to try | Why |
|---|---|---|
| **Read-heavy** | Scale up the cluster tier | Bigger CPU and more cache per shard makes reads faster without spreading the working set thin |
| **Write-heavy** | Scale up the storage SKU first, then scale out | Bigger SKUs deliver more IOPS per shard; scale out only when one shard's IOPS is exhausted |
| **Storage-bound** | Scale up the storage SKU first; scale out when projection exceeds one shard's ceiling | A single shard up to 32 TB is cheaper to run than two 16 TB shards |
| **Mixed, growing** | Scale up to the right per-shard size first, then scale out when one shard is no longer enough | Avoid premature sharding |

## Incorrect

```text
☐ Scaling out a read-heavy workload to "spread the load."
  → Reads localize to one physical shard when the query includes the shard key.
    Spreading across more shards just shrinks each shard's cache.

☐ Scaling out to fix a hot logical shard.
  → A logical shard lives on exactly one physical shard. Adding nodes doesn't
    move it. Fix the shard key first.

☐ Mixing cluster tiers across physical shards.
  → Not possible. All physical shards in a cluster are identically sized.

☐ Treating scale-out as zero-cost.
  → It triggers a rebalance; plan for the data-movement window and monitor
    replication lag / cluster state during the operation.

☐ Skipping scale-up and going straight to scale-out for a 100 GB collection.
  → Scale-up is reversible and doesn't move data. Try it first.
```

## Correct

### Decision sequence for a saturated cluster

1. **Identify the bottleneck.** CPU? Memory / cache miss rate? IOPS? Storage? Per-shard or cluster-wide?
2. **If a single physical shard is saturated and others are idle**: hot partition. Don't scale anything yet — fix the shard key. See [sharding-hot-partition-diagnosis](sharding-hot-partition-diagnosis.md).
3. **If all physical shards are roughly equally saturated and you're not at the top tier / SKU**: scale up. Reassess after the change.
4. **If all physical shards are saturated *at* the top tier / SKU**: scale out. Plan the rebalance window.
5. **If queries are scatter-gather (no shard-key filter)**: scaling out makes it worse. Fix the queries first.

## References

- [Capacity of physical shards](https://learn.microsoft.com/azure/documentdb/partitioning#capacity-of-physical-shards)
- [Mapping logical shards to physical shards](https://learn.microsoft.com/azure/documentdb/partitioning#mapping-logical-shards-to-physical-shards)
- [Compute and storage in Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/compute-storage)
- Related: [sharding-logical-vs-physical](sharding-logical-vs-physical.md), [sharding-hot-partition-diagnosis](sharding-hot-partition-diagnosis.md)
