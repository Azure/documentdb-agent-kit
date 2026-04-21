# index-lifecycle-drop-hide

**Category:** Indexing · **Priority:** HIGH

## Why it matters

Indexes are not write-once: they accumulate. After a few releases you'll have indexes created for queries that no longer exist, duplicates from someone running `createIndex` twice with different names, and single-field indexes that a later compound index has made redundant. Every one of them costs writes and memory.

Safe index removal follows a three-step loop:

1. **Measure** — list indexes and their usage (`getIndexes`, `$indexStats`).
2. **Hide** — make the index invisible to the planner without dropping it (`hideIndex`).
3. **Drop** — once you've confirmed in production that nothing regresses, `dropIndex`.

The `_id` index cannot be dropped.

## Incorrect

Dropping an index cold, based on a guess, during peak traffic:

```javascript
db.products.dropIndex("category_1_price_1");
// Ten minutes later: P99 on the product listing page spikes 40x.
// Rebuilding the index on a large collection takes real time.
```

Keeping obvious redundants around "just in case":

```javascript
db.products.createIndex({ category: 1 });              // later made redundant by ↓
db.products.createIndex({ category: 1, price: 1 });    // covers the prefix above

// The single-field `category_1` is a prefix of `category_1_price_1` and serves
// no query the compound one doesn't. Every write still maintains both.
```

## Correct

### Step 1 — inventory

```javascript
db.products.getIndexes();
// Review names, keys, options, and any `partialFilterExpression`.

db.products.aggregate([
  { $indexStats: {} },
  { $project: { name: 1, key: 1, "accesses.ops": 1, "accesses.since": 1 } },
  { $sort: { "accesses.ops": 1 } }
]);
// Indexes with `ops: 0` and a `since` date older than a full traffic cycle
// (typically ≥ 1 week) are deletion candidates.
```

### Step 2 — detect redundancy

Common redundant shapes:

- **Prefix redundancy.** A single-field `{ a: 1 }` is redundant when a compound `{ a: 1, b: 1 }` exists.
- **Direction redundancy.** `{ a: 1 }` and `{ a: -1 }` serve the same single-field queries; keep one.
- **Near-duplicates.** Two indexes with the same key pattern under different names (often from repeated `createIndex` with different `name:` options).

```javascript
db.products.createIndex({ category: 1, price: 1 });
db.products.dropIndex("category_1");     // redundant prefix of the compound
```

### Step 3 — hide before drop

Use `hideIndex` as a cheap, fully-reversible dry run. The index still receives writes, but the planner ignores it — you get the read-path effect of `dropIndex` without the cost of rebuilding if you were wrong.

```javascript
db.products.hideIndex("old_field_1");

// Now monitor for a full traffic cycle:
// - slow-query log for regressions
// - explain() on critical queries (no unexpected COLLSCAN)
// - latency dashboards

// If clean:
db.products.dropIndex("old_field_1");

// If regressions appear:
db.products.unhideIndex("old_field_1");
```

### Step 4 — drop off-peak, and record why

```javascript
db.products.dropIndex("old_field_1");
// Commit a note somewhere durable (CHANGELOG, ADR, runbook):
//   "2026-04: dropped products.old_field_1 — 0 ops over 14d, redundant with
//    category_1_price_1."
```

If you drop the wrong one, recreate it:

```javascript
db.products.createIndex(
  { category: 1, price: -1 },
  { name: "cat_price_idx" }
);
// Use a descriptive name so next quarter's audit understands the intent.
```

### What you cannot drop

```javascript
db.products.dropIndex("_id_");
// { ok: 0, errmsg: "cannot drop _id index", code: 72 }
```

## Audit cadence

Run the measure → hide → drop loop quarterly, and always after:

- a large query-shape change (new sort, new filter field),
- a data-modeling refactor (embedding ↔ referencing),
- adding or removing a feature that backed a specific index.

Keep per-collection index count in the 5–15 range (see [index-count-budget](index-count-budget.md)). If `db.coll.stats().totalIndexSize` is approaching `size`, you're over-indexed.

## References

- [`$indexStats`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/)
- [`hideIndex` / `unhideIndex`](https://www.mongodb.com/docs/manual/core/index-hidden/)
- [`dropIndex` / `dropIndexes`](https://www.mongodb.com/docs/manual/reference/method/db.collection.dropIndex/)
