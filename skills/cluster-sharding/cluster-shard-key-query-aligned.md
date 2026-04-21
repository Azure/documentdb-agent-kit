# cluster-shard-key-query-aligned

**Category:** Cluster Design & Sharding · **Priority:** CRITICAL

## Why it matters

When a DocumentDB collection does need explicit sharding (see `cluster-scale-before-shard`), the shard key decides how data and load distribute. Low-cardinality or monotonically increasing keys concentrate writes and reads on a small set of physical shards, producing hot nodes and tail-latency spikes. A shard key is effectively **immutable** once chosen — re-sharding is a heavyweight migration.

Pick a shard key with:

1. **High cardinality** — many distinct values.
2. **Even frequency** — no value dominates the distribution.
3. **Query alignment** — appears in the filter of hot-path queries so they are targeted, not scatter-gather.
4. **Immutability** — value never changes after document creation.

## Incorrect

```javascript
// Low cardinality — only a few values concentrate load
db.orders.shardCollection({ status: 1 });

// Monotonic — every new write hits the newest chunk (hot write shard)
db.events.shardCollection({ createdAt: 1 });

// Shard key absent from common queries -> scatter-gather
db.orders.shardCollection({ customerId: "hashed" });
db.orders.find({ email: "ada@example.com" });
```

## Correct

```javascript
// High-cardinality, query-aligned, immutable
db.orders.shardCollection({ customerId: "hashed" });
db.orders.find({ customerId, status: "open" }); // targeted

// Composite key when one field isn't enough
db.events.shardCollection({ tenantId: 1, eventId: "hashed" });
```

If a hot query genuinely can't include the shard key, maintain a small secondary lookup collection keyed by that field to get back a shard-key value, then do a targeted fetch.

## References

- [Scale a cluster](https://learn.microsoft.com/azure/documentdb/how-to-scale-cluster)
- [MQL compatibility — sharding](https://learn.microsoft.com/azure/documentdb/compatibility-query-language)
