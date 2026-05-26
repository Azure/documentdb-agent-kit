# index-hashed-shard-keys

**Category:** Indexing · **Priority:** MEDIUM

## Why it matters

Sharding is the **scale-out** strategy for Azure DocumentDB — partitioning a collection across multiple nodes by a **shard key** so that storage and throughput grow horizontally. In Azure DocumentDB, sharding is only needed for very high throughput workloads or storage above **32 TB**; below that, a single cluster tier handles it. Choosing `"hashed"` as the shard key type distributes writes evenly regardless of the key's natural ordering, avoiding hot-spots caused by monotonically increasing values (e.g., `ObjectId`, `createdAt`).

As a consequence, DocumentDB creates a **hashed index** on the chosen field. Internally, the hash value is stored as part of a composite index alongside `_id`, which is what routes each document to the correct shard.

When you do shard, hashed vs ranged is the first decision:

| Property | Hashed shard key | Ranged shard key |
|---|---|---|
| Write distribution | Very even | Can hot-spot on monotonic keys |
| Equality queries | Fast (single shard) | Fast (single shard) |
| Range queries (`$gt` / `$lt`) | **Scatter-gather — every shard** | Targeted (adjacent shards) |
| Sort by shard key | No | Yes |

## Incorrect

Hashing a field you routinely query by range:

```javascript
sh.shardCollection("app.events", { createdAt: "hashed" });
// Then: db.events.find({ createdAt: { $gte: <lastHour> } }).sort({ createdAt: -1 })
// Every shard is queried; sort is in-memory. Defeats the purpose of sharding by this field.
```

Using a hashed index for anything other than shard-key support:

```javascript
db.users.createIndex({ email: "hashed" });   // normal user lookup
db.users.find({ email: "alice@example.com" });
// A regular index on email is faster and supports range/prefix queries too.
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

For **query-driven** workloads (orders by customer, posts by author), prefer a ranged shard key aligned with the dominant access pattern.

Guidelines:

- Match the shard key to the **most common query's equality filter**. If that filter is an ID, a hashed key is usually fine.
- Never hash a field you need to sort or range-scan.
- Hashed shard keys must be on a single field; no compound hashed shard keys.

## References

- [MongoDB hashed indexes](https://www.mongodb.com/docs/manual/core/index-hashed/)
