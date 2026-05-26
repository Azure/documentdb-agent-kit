# sharding-shard-key-selection

**Category:** Sharding · **Priority:** HIGH

## Why it matters

The shard key is the **single biggest determinant of a sharded collection's long-term performance.** Every document is hashed by its shard-key value, and the hash determines which physical shard owns the document — so the key controls both **data distribution** (how evenly storage and writes spread across the cluster) and **query routing** (whether a query can be served by one physical shard or has to scatter-gather across all of them).

Once a collection is large, **changing the shard key is expensive** (`sh.reshardCollection` rewrites the data, see [sharding-how-to-commands](sharding-how-to-commands.md)). Treat the choice as if it were permanent.

## The two workload archetypes

Pick the strategy that matches your workload **before** running `sh.shardCollection`.

### Read-heavy workloads → align with the most frequent query filter

If the workload is dominated by reads, the goal is to **localize the highest-volume queries to a single physical shard**. Pick the field that appears in the largest fraction of query filters as the shard key. Queries that include that field will be routed to one physical shard; queries that don't will scatter-gather across all of them and pay an N-way fan-out.

**Example**: a multi-tenant SaaS app where 95% of queries filter by `tenantId`. Sharding on `tenantId` means almost every query hits one physical shard — fast, predictable, cache-friendly. Sharding on a different field (e.g., `documentId`) makes those 95% of queries scatter-gather.

Tradeoff: if `tenantId` distribution is skewed (a few huge tenants), this strategy can hot-spot — see [sharding-hot-partition-diagnosis](sharding-hot-partition-diagnosis.md).

### Write-heavy workloads → maximize cardinality and even distribution

If write throughput is the bottleneck, the goal is to **spread writes evenly across all physical shards** so no single shard becomes a hot writer. Pick the **highest-cardinality field** in the document — i.e., the one with the most unique values — and verify the distribution is actually even (not just high-cardinality on paper but skewed in practice).

**Example**: an event-ingest workload that writes 100 K events/sec. Sharding on `eventId` (a high-cardinality random GUID) distributes writes evenly. Sharding on `eventType` (a low-cardinality enum) concentrates writes onto a few physical shards.

Tradeoff: queries that filter by `eventType` instead of `eventId` will scatter-gather. Write-heavy workloads accept this read tax to keep write throughput linear with cluster size.

## Anti-patterns: shard keys that almost always hurt

| Anti-pattern | Why it hurts |
|---|---|
| **Monotonically increasing values** (auto-increment IDs, `_id` as `ObjectId`, timestamps) | With **ranged** sharding, all new writes target the shard owning the highest range — single-shard write hotspot. With **hashed** sharding (the DocumentDB default — see [`indexing/index-hashed-shard-keys`](../indexing/index-hashed-shard-keys.md)) writes distribute evenly, but **reads** still cluster temporally on whatever shard owns "recent" data, so range / time-window queries scatter-gather and dashboards on "last hour" hit one shard. |
| **Timestamps** (`createdAt`, `eventTime`) | Same problem as any monotonic key — even with hashed sharding, range queries on the timestamp scatter-gather and recent-data reads concentrate on a small subset of shards. |
| **Low-cardinality enum** (`status`, `type`, `region` with 3 values) | Only as many distinct hash buckets as there are values; data distributes onto at most that many physical shards. |
| **Skewed high-cardinality** (`tenantId` with 80 % of traffic on one tenant) | High cardinality on paper, but the **distribution** is what matters. One tenant's shard becomes a hot partition. |
| **Fields that are sometimes missing** | Documents without the shard-key field can't be sharded — sharding requires the key on every document. |

## Cardinality + distribution = the real metric

"High cardinality" alone is not enough. What you actually want is **high cardinality with even distribution of both storage and request volume across keys**. Measure both before choosing:

- `db.<collection>.aggregate([{$sortByCount: "$<candidate-key>"}])` — confirms the top-N keys aren't dominant.
- Application traces / metrics — confirms request volume per key isn't dominated by a handful of values.

If a candidate key has high cardinality but one value covers >5–10 % of storage or requests, it'll create a hot partition. Either pick a different key, or build a **composite shard key** (e.g., hash of `{tenantId, eventId}`) that adds entropy.

## Incorrect

```text
☐ Sharding on _id (default ObjectId).
  → ObjectId is monotonic - new writes hit one shard. Hashed sharding helps writes
    but reads still cluster temporally.

☐ Sharding on createdAt or any timestamp.
  → Same temporal-locality problem. Hot shard for recent data.

☐ Sharding on a Boolean or low-cardinality enum.
  → Only 2 / N distinct hash buckets - data fits onto at most 2 / N physical shards.

☐ Picking the shard key based on a query that "feels common" without measuring.
  → Pull actual query distribution from logs or query stats first.

☐ Sharding on a field that's optional in some documents.
  → Sharding requires the key on every document. Backfill or pick a field that's
    always present.

☐ Forgetting to create the index on the shard-key field.
  → `sh.shardCollection` does not auto-create the index. Without it, queries that
    should localize to one shard will scatter-gather.
```

## Correct

### 1. Identify the workload archetype with data, not intuition

Before picking a key, capture:

- **Read/write ratio** — query a representative time window.
- **Top query filters** — what fields appear in `find` / aggregate `$match` filters, weighted by frequency.
- **Top write paths** — which fields are present on every insert.

If reads dominate **and** one field appears in the majority of query filters, you're in the read-heavy archetype.

If writes dominate **or** queries are diverse with no clear most-common filter, you're in the write-heavy archetype.

### 2. Validate cardinality *and* distribution

For each candidate field:

```javascript
db.employee.aggregate([
  { $group: { _id: "$candidateKey", count: { $sum: 1 } } },
  { $sort: { count: -1 } },
  { $limit: 20 }
])
```

The top-20 buckets should each contain a small percentage of total documents. If the top bucket is > 5–10 %, that key will hot-spot.

### 3. Build a composite shard key when no single field works

If the natural query field (e.g., `tenantId`) is skewed, combine it with a high-cardinality field. Two common shapes:

- **Hashed composite**: precompute `shardKey = hash(tenantId + ":" + recordId)` in the application and store it as a top-level field. Shard on that field with `"hashed"`.
- **Multi-field shard key**: use a compound shard key like `{tenantId: "hashed", recordId: 1}` (where supported) so within-tenant queries still localize but the overall distribution evens out.

### 4. Index the shard key explicitly

```javascript
db.runCommand({
  createIndexes: "employee",
  indexes: [{
    key: { firstName: 1 },
    name: "firstName_1",
    enableLargeIndexKeys: true
  }],
  blocking: true
})
```

The index is required for the shard key to be queryable efficiently. `enableLargeIndexKeys: true` is the safe default for arbitrary shard-key values. Cross-link: [sharding-how-to-commands](sharding-how-to-commands.md).

### 5. Decision matrix

| Workload signal | Pick this kind of key |
|---|---|
| 90 % of queries filter on the same field, distribution is even | That field, hashed |
| Same as above but distribution is skewed | Composite (skewed field + high-cardinality field) |
| Writes dominate, no clear query filter pattern | Highest-cardinality field with verified even distribution |
| Multi-tenant with even tenant sizes | `tenantId`, hashed |
| Multi-tenant with skewed tenant sizes | Composite of `tenantId` + record ID |
| Time-series ingest, recent-data reads | Composite (entity ID + bucketed time), **not raw timestamp** |

## References

- [Sharding — Best practices](https://learn.microsoft.com/azure/documentdb/partitioning#best-practices-for-sharding-data)
- [Sharding — How to shard a collection](https://learn.microsoft.com/azure/documentdb/partitioning#how-to-shard-a-collection)
- Related: [sharding-hot-partition-diagnosis](sharding-hot-partition-diagnosis.md), [sharding-how-to-commands](sharding-how-to-commands.md)
