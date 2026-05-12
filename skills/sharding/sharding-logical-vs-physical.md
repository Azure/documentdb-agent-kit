# sharding-logical-vs-physical

**Category:** Sharding · **Priority:** MEDIUM

## Why it matters

The terms *logical shard* and *physical shard* sound interchangeable but describe two different things, and getting the model wrong leads to bad capacity decisions. The short version:

- **Logical shards** are addressing buckets created by hashing the shard key. They are unbounded in count and size and exist purely as a service-internal mapping.
- **Physical shards** are real nodes — CPU, memory, disk, IOPS — and they own ranges of the hash space. Multiple logical shards map to one physical shard; **a logical shard is never split across physical shards**.

Capacity is governed by physical shards. Distribution is governed by the shard key, via logical shards. You need both layers in your head to reason about performance.

## The model

```
        ┌──────────────────────────────────────────┐
        │     shard key value → hash function      │
        └──────────────────────────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────────┐
        │            LOGICAL SHARDS                │
        │   (one per unique shard-key value)       │
        │   unbounded count · unbounded size       │
        └──────────────────────────────────────────┘
                            │
                            │  service-managed mapping
                            ▼
        ┌──────────────────────────────────────────┐
        │           PHYSICAL SHARDS                │
        │  (real nodes; each owns an even slice    │
        │   of the hash range)                     │
        │  count fixed at creation, can grow       │
        │  capacity = cluster tier × storage SKU   │
        └──────────────────────────────────────────┘
```

### Logical shards

- A logical shard is the set of all documents that share a single shard-key value.
- The number of logical shards equals the number of distinct shard-key values in the collection.
- **The service imposes no limit on the number of logical shards** and no hard limit on the size of any single logical shard.
- For best performance, keep an individual logical shard **under 4 TB** — see [sharding-logical-shard-size-budget](sharding-logical-shard-size-budget.md).
- Cross-shard transactions (across both logical and physical shards) are supported — DocumentDB is **not** restricted to single-logical-shard transactions like some MongoDB versions.

### Physical shards

- A physical shard is the actual node (a replica set, see below) that stores some range of the hash space and serves transactions against documents in that range.
- The number of physical shards is **chosen at cluster creation** and can be increased later. It is **never reduced** automatically; scale-in is a separate operation.
- Each physical shard's compute / memory is determined by the **cluster tier**; its storage and IOPS are determined by the **storage SKU**. All physical shards in a multi-shard cluster have **identical capacity**.
- Logical shards map to physical shards by their hash value falling inside the physical shard's hash range. The service handles this mapping; you cannot pin a logical shard to a specific physical shard.
- **A logical shard is never split across physical shards.** All documents for a given shard-key value live on exactly one physical shard, even if that logical shard is large.

### Replica sets — within each physical shard

Each physical shard is itself a **replica set** — multiple replicas of the same data, each running an instance of the database engine. Replica sets give the physical shard:

- **Durability** — multiple copies of every write.
- **High availability** — a replica can take over if the primary fails.
- **Consistency** — managed by the service.

You do not configure replica sets directly. The number, placement, and management of replicas inside a physical shard are owned by the service. The replica set lives **inside** the physical shard, not across physical shards.

## Why "one logical shard per physical shard" is wrong

A common misreading of "multiple logical shards map to one physical shard" is to invert it: *if I just have one logical shard, can I pin it to one physical shard?* No — and that's not even the model. The mapping is many-to-one (logical → physical), never one-to-one or one-to-many:

- A physical shard holds **many** logical shards (typically thousands).
- A logical shard lives on **exactly one** physical shard.

If a single logical shard grows large enough to dominate a physical shard's storage or throughput, **you have a hot partition** — see [sharding-hot-partition-diagnosis](sharding-hot-partition-diagnosis.md). The fix is to pick a higher-cardinality shard key (more, smaller logical shards), not to ask the service to split the logical shard.

## Practical implications

### 1. Capacity = (physical shards) × (per-shard capacity)

When you size a sharded cluster, multiply: `total CPU ≈ tier × shard count`, `total storage ≈ SKU × shard count`. Logical shards don't enter the formula because they don't carry their own capacity.

### 2. Skew shows up at the physical layer

If one physical shard is reporting 80 % CPU while the others are at 20 %, your shard-key distribution is uneven at the *logical* layer — but you only see it at the *physical* layer. Look at logical-shard size and request distribution via metrics; the fix is upstream at the shard key.

### 3. Cross-shard queries pay a fan-out tax

A query that doesn't include the shard key has to scatter-gather across **every** physical shard, wait for the slowest, and merge results. The number of logical shards doesn't matter — what matters is the physical-shard count. The more physical shards, the more expensive the fan-out.

### 4. Transactions across shards work, but plan for them

Multi-document / multi-shard transactions are supported but cost more than single-shard transactions. Prefer designs where transactional units (e.g., all documents touched by one business operation) live in the same logical shard. With the right shard key, they will also live on the same physical shard automatically.

## References

- [Logical shards — Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/partitioning#logical-shards)
- [Physical shards — Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/partitioning#physical-shards)
- [Compute and storage in Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/compute-storage)
- Related: [sharding-shard-key-selection](sharding-shard-key-selection.md), [sharding-scaling-out-vs-up](sharding-scaling-out-vs-up.md), [sharding-hot-partition-diagnosis](sharding-hot-partition-diagnosis.md)
