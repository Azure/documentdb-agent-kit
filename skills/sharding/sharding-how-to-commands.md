# sharding-how-to-commands

**Category:** Sharding · **Priority:** MEDIUM

## Why it matters

The commands to shard or reshard a collection are simple — three lines of mongo shell — but each has a precondition that, if skipped, costs hours or breaks production. This rule is the cheat sheet for the actual commands plus the pre- and post-flight checks that have to go with them.

## Pre-flight checklist (before `sh.shardCollection`)

1. **Decide the shard key with data, not intuition** — see [sharding-shard-key-selection](sharding-shard-key-selection.md).
2. **Confirm the field is present on every document** — sharding requires the shard-key field on every document in the collection. Backfill missing values first.
3. **Create the index on the shard-key field** with `enableLargeIndexKeys: true`. The shard command does **not** auto-create the index, and a missing index forces queries to scatter-gather.
4. **For an existing large collection**: budget a maintenance window. The initial shard operation rewrites the collection's placement and triggers data movement.

## Shard a collection

Given a collection `cosmicworks.employee` whose documents include a `firstName` field:

```javascript
use cosmicworks;

// 1. Create the index first
db.runCommand({
  createIndexes: "employee",
  indexes: [{
    key: { firstName: 1 },
    name: "firstName_1",
    enableLargeIndexKeys: true
  }],
  blocking: true
})

// 2. Shard the collection (helper form)
sh.shardCollection("cosmicworks.employee", { firstName: "hashed" })
```

The same operation via the admin-command form (useful from drivers that don't expose `sh.*` helpers):

```javascript
use cosmicworks;
db.adminCommand({
  shardCollection: "cosmicworks.employee",
  key: { firstName: "hashed" }
})
```

**Notes**:

- `"hashed"` is the recommended default — it distributes data evenly across the hash range and avoids write hot-spotting on monotonic keys. **Ranged** shard keys (`{ field: 1 }`) preserve locality for range and sort queries on the shard-key field; consider them only when range/time-window queries on the shard key dominate the workload *and* the field is not monotonically increasing. See [`indexing/index-hashed-shard-keys`](../indexing/index-hashed-shard-keys.md) for the hashed-vs-ranged tradeoff matrix.
- The fully-qualified `database.collection` name is required.
- The collection can be empty or populated. If populated, the operation rewrites placement — expect a data-movement window proportional to collection size.

## Change the shard key (reshard)

If you need to change the shard key after the collection is sharded — typically to fix a hot partition (see [sharding-hot-partition-diagnosis](sharding-hot-partition-diagnosis.md)) — use `sh.reshardCollection`:

```javascript
use cosmicworks;

// 1. Create the index on the NEW shard key first
db.runCommand({
  createIndexes: "employee",
  indexes: [{
    key: { lastName: 1 },
    name: "lastName_1",
    enableLargeIndexKeys: true
  }],
  blocking: true
})

// 2. Reshard
sh.reshardCollection("cosmicworks.employee", { lastName: "hashed" })
```

Admin-command form:

```javascript
use cosmicworks;
db.adminCommand({
  reshardCollection: "cosmicworks.employee",
  key: { lastName: "hashed" }
})
```

**Resharding is expensive.** The entire collection is rewritten with the new hash mapping. On a multi-TB collection this can take hours and stresses cluster CPU and I/O the whole time. Treat it as a planned maintenance operation:

- Schedule during a low-traffic window.
- Monitor replication lag and replica-set health throughout.
- Validate the new distribution after completion (CPU / IOPS / storage should be even across physical shards).

## The shard-key index requirement

This trips people up often enough to call out explicitly. **Sharding requires an index on the shard-key field, and creating the shard does NOT create the index for you.** Always:

```javascript
db.runCommand({
  createIndexes: "<collection>",
  indexes: [{
    key: { <shardKeyField>: 1 },
    name: "<shardKeyField>_1",
    enableLargeIndexKeys: true
  }],
  blocking: true
})
```

- `enableLargeIndexKeys: true` is the safe default — without it, any document where the shard-key value's BSON-encoded size exceeds the standard index-key limit will fail to insert. Belt-and-suspenders.
- `blocking: true` makes the index build foreground (predictable but locks writes); use foreground for the shard-key index since the collection is presumably not yet at heavy write load (you're about to shard it).
- The index name follows the standard `<field>_<direction>` convention.

If you later realize you sharded without the index (don't), create it immediately with the same command. Until it exists, queries filtering on the shard key won't localize properly.

## Post-shard validation

After `sh.shardCollection` or `sh.reshardCollection` completes:

1. **Confirm the collection is sharded** — `db.<collection>.getShardDistribution()` (or equivalent) should report multiple physical shards each holding a roughly equal share of documents and bytes.
2. **Check CPU / IOPS / storage across physical shards** in cluster metrics. Even distribution within ~10 % is healthy. Sharp imbalance indicates a hot-partition shape — see [sharding-hot-partition-diagnosis](sharding-hot-partition-diagnosis.md).
3. **Re-`explain()` the most common queries.** Queries filtering on the shard key should report routing to a single physical shard. Queries that don't include the shard key are expected to scatter-gather — confirm that's intentional.
4. **Watch for write-amplification** on the shard-key index — a heavily updated shard-key field is a smell that the wrong key was chosen.

## Incorrect

```text
☐ Running sh.shardCollection without first creating the shard-key index.
  → The command succeeds but queries that should localize will scatter-gather.
    Create the index, ideally before sharding.

☐ Running sh.reshardCollection on a multi-TB collection during peak traffic.
  → Resharding rewrites the whole collection. Schedule a maintenance window.

☐ Sharding a collection whose shard-key field is missing on some documents.
  → Backfill the field on every document first. Sharding requires the key
    everywhere.

☐ Sharding via the helper form and admin command form in the same script.
  → Pick one. They do the same thing - using both is a sign of copy-paste from
    two different sources and risks confusion.

☐ Resharding to fix a problem without verifying the new key's distribution.
  → You might move from one bad shape to another. Measure cardinality AND
    distribution on the candidate key first (see sharding-shard-key-selection).
```

## References

- [How to shard a collection — Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/partitioning#how-to-shard-a-collection)
- Related: [sharding-shard-key-selection](sharding-shard-key-selection.md), [sharding-hot-partition-diagnosis](sharding-hot-partition-diagnosis.md), `indexing/` skill
