# index-hashed-shard-keys

**Category:** Indexing · **Priority:** MEDIUM

## Why it matters

A **hashed index** (`{ field: "hashed" }`) stores a hash of the field's value instead of the raw value. Its main purpose is enabling **hashed shard keys**, which distribute writes evenly across shards — essential when a monotonically increasing key (e.g., `_id: ObjectId()`, `createdAt`) would otherwise hot-spot a single shard.

In Azure DocumentDB, an explicit shard key isn't required until the database grows past terabyte scale (see `cluster-sharding/cluster-scale-before-shard`). When you do shard, hashed vs ranged is the first decision:

| Property | Hashed shard key | Ranged shard key |
|---|---|---|
| Write distribution | Very even | Can hot-spot on monotonic keys |
| Equality queries | Fast (single shard) | Fast (single shard) |
| Range queries (`$gt` / `$lt`) | **Scatter-gather — every shard** | Targeted (adjacent shards) |
| Sort by shard key | No | Yes |

## Incorrect

Hashing a field you routinely query by range:

```javascript
db.events.createIndex({ createdAt: "hashed" });
// Then: db.events.find({ createdAt: { $gte: <lastHour> } }).sort({ createdAt: -1 })
// Every shard is queried; sort is in-memory. Defeats the point of a shard key.
```

Using a hashed index for anything other than shard-key support:

```javascript
db.users.createIndex({ email: "hashed" });   // normal user lookup
db.users.find({ email: "alice@example.com" });
// A regular b-tree index on email is faster and supports range/prefix queries too.
```

## Correct

Use a hashed shard key when writes dominate and queries are predominantly point lookups on the shard key:

```javascript
sh.shardCollection("app.events", { _id: "hashed" });
// Writes: spread evenly across shards.
// Reads of form find({ _id: X }): single shard, fast.
// Analytics queries scanning a time range: use a separate time-bucketed collection
// or accept scatter-gather.
```

For **query-driven** workloads (orders by customer, posts by author), prefer a ranged shard key aligned with the dominant access pattern — see `cluster-sharding/cluster-shard-key-query-aligned`.

Guidelines:

- Match the shard key to the **most common query's equality filter**. If that filter is an ID, a hashed key is usually fine.
- Never hash a field you need to sort or range-scan.
- Hashed shard keys must be on a single field; no compound hashed shard keys.

## References

- [MongoDB hashed indexes](https://www.mongodb.com/docs/manual/core/index-hashed/)
- `cluster-sharding/cluster-shard-key-query-aligned.md`
