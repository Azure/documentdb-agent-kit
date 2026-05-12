# sharding-hot-partition-diagnosis

**Category:** Sharding · **Priority:** HIGH

## Why it matters

A **hot partition** (or hot shard) is when one physical shard is doing significantly more work — storage, CPU, IOPS, or all three — than its peers in the cluster. Because every physical shard in a DocumentDB cluster is identically sized (see [sharding-scaling-out-vs-up](sharding-scaling-out-vs-up.md)), a hot shard is the cluster's de facto ceiling: throughput is capped by the slowest shard, regardless of how much headroom the others have.

Hot partitions are almost always **a shard-key problem in disguise**. They don't go away with bigger nodes, more nodes, or better indexes — those treat symptoms. The fix is upstream, at the shard key.

## Symptoms

You probably have a hot partition if one or more of these signals is consistently true:

| Signal | What it looks like |
|---|---|
| **Uneven CPU across physical shards** | One shard at 80–100 %, others at 20–40 % |
| **Uneven storage across physical shards** | One shard at 70 % full, others at 20–30 % |
| **Uneven IOPS across physical shards** | One shard hitting its IOPS ceiling, others coasting |
| **Throttling concentrated on one shard** | Latency / error spikes localized to a subset of clients (those whose requests route to the hot shard) |
| **Scale-out didn't help** | You added physical shards and the hot shard's metrics didn't drop — its logical-shard load just stayed put |

The first three are visible directly in cluster metrics. The fourth is application-level. The fifth is the diagnostic confirmation.

## Root causes

Every hot partition reduces to **one of these shard-key shapes**:

1. **Low cardinality.** The shard key has very few distinct values, so only a few hash buckets exist, and they don't spread across all physical shards. Example: sharding on `region` with values {us, eu, asia}.
2. **Skewed distribution.** The key has high cardinality on paper but one or two values dominate the data. Example: sharding on `tenantId` where one tenant produces 60 % of the writes.
3. **Monotonic / temporal locality.** The key is increasing over time (ObjectId, timestamp, sequence number). Hashed sharding spreads *writes* evenly, but reads tend to focus on recent values, hot-spotting the physical shard that owns the current hash bucket.
4. **Composite key with skewed leading field.** The shard key is `{tenantId, recordId}` but `tenantId` is so skewed that the composite is dominated by one prefix.

If you find a hot shard, work back through this list to find which shape applies — the remediation depends on which one.

## Diagnosis: confirm it's a shard-key problem, not something else

Before resharding, rule out cheaper causes:

1. **Is one query pattern doing collection scans?** A single bad query can saturate one shard if it happens to route there. Run query stats / `explain()` on the heaviest queries. See `query-optimization/`.
2. **Is the index missing on the shard key?** If queries that include the shard key still scatter-gather, the index didn't get created (or got dropped). See [sharding-how-to-commands](sharding-how-to-commands.md).
3. **Is a background job concentrated on one shard's data?** E.g., a nightly export filtering on one tenant. Reschedule or batch differently before resharding.
4. **Confirm the metric is sustained, not a spike.** A 10-minute hot shard from a backup job isn't worth a reshard. A multi-day pattern is.

If you've ruled all of those out, the shard key is the problem.

## Remediation: shard-key shape → fix

### Shape 1 — Low cardinality

Pick a higher-cardinality key, or **compose** the existing key with a high-cardinality field. Example: instead of sharding on `region`, shard on `{region, userId}` (so within a region you still spread across users) or compute a top-level `regionUser = region + ":" + userId` field and shard on that.

### Shape 2 — Skewed distribution

The classic case. Three options, in increasing order of effort:

- **(a) Compose with a high-cardinality field.** Shard on `{tenantId, recordId}` or store a top-level `compositeKey = hash(tenantId, recordId)` and shard on that. Queries that filter on the full composite still localize; queries that filter only on `tenantId` scatter (acceptable tax if those are rare).
- **(b) Move to a different field entirely.** If `tenantId` skew can't be fixed and there's another high-cardinality, evenly-distributed field, shard on that.
- **(c) Isolate the hot tenant.** Some teams move dominant tenants to their own collections or clusters. Operationally heavier but avoids resharding the shared collection.

### Shape 3 — Monotonic / temporal locality

Stop sharding on the timestamp / sequence directly. Common fixes:

- **Bucketed time + entity ID composite.** Shard on `{entityId, timeBucket}` where `timeBucket` is e.g. day-resolution. Recent reads now spread across whatever entities are active in the current bucket.
- **Pure entity ID.** If entity IDs are themselves high-cardinality and evenly distributed, drop the time component from the shard key and rely on a secondary index on `createdAt` for time-range queries.

### Shape 4 — Composite with skewed leading field

The leading field of the composite dominates the hash distribution. Either reorder the composite so the high-cardinality field leads (where the workload permits), or replace the composite with a single hashed surrogate key (`shardKey = hash(allFields)`).

## Executing the reshard

Once you've picked the new key:

1. **Create the index on the new key first** (`createIndexes` with `enableLargeIndexKeys: true`).
2. **Run `sh.reshardCollection`** with the new key — see [sharding-how-to-commands](sharding-how-to-commands.md).
3. **Plan for a data-movement window.** Resharding rewrites the collection; monitor cluster CPU, replication lag, and replica-set health throughout. Avoid resharding during peak hours on large collections.
4. **Validate after**: re-check the same metrics that flagged the hot partition. CPU / IOPS / storage should now be even across shards within a few hours of the reshard completing.

## Incorrect

```text
☐ Scaling out to "absorb" a hot partition.
  → A logical shard lives on exactly one physical shard. Adding nodes doesn't
    split it - the hot shard stays hot, you just paid for more idle shards.

☐ Scaling up the tier to "give the hot shard more CPU."
  → Scale-up applies to ALL physical shards equally. You pay 4x for the upgrade
    to fix one shard.

☐ Adding more indexes to "speed up" the hot shard's queries.
  → Doesn't change the shard-key distribution. May actually make it worse by
    adding write amplification on the already-busy shard.

☐ Resharding without measuring distribution on the new candidate key.
  → You might be moving from one skewed key to another. Validate cardinality
    AND distribution before committing - see sharding-shard-key-selection.

☐ Resharding in production during peak hours.
  → The data-movement window stresses the cluster. Schedule it during a low-traffic
    window and pre-stage on a non-prod copy first if the collection is large.
```

## References

- [Capacity of physical shards](https://learn.microsoft.com/azure/documentdb/partitioning#capacity-of-physical-shards) — uneven utilization caveat
- [Sharding — Best practices](https://learn.microsoft.com/azure/documentdb/partitioning#best-practices-for-sharding-data)
- Related: [sharding-shard-key-selection](sharding-shard-key-selection.md), [sharding-how-to-commands](sharding-how-to-commands.md), [sharding-scaling-out-vs-up](sharding-scaling-out-vs-up.md)
