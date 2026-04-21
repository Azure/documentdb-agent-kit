# index-count-budget

**Category:** Indexing · **Priority:** MEDIUM

## Why it matters

Each index pays a recurring cost — **every insert, update, and delete updates every relevant index**, and indexes consume disk and working-set memory. Adding indexes looks free in isolation; the bill arrives at write time. A healthy collection typically has **5–15 purpose-built indexes**. Well past that, write throughput drops and the planner starts making worse choices.

Don't "index every field just in case". Index the fields queries actually filter, sort, or enforce uniqueness on, and drop what's unused.

## Incorrect

One index per field on a hot-write collection:

```javascript
db.products.createIndex({ name: 1 });
db.products.createIndex({ brand: 1 });
db.products.createIndex({ category: 1 });
db.products.createIndex({ price: 1 });
db.products.createIndex({ rating: 1 });
db.products.createIndex({ stock: 1 });
db.products.createIndex({ sku: 1 });
// 7 indexes (+ _id). Every insert/update now maintains 8 indexes.
// Most of these never serve a query that actually runs in production.
```

Leaving indexes behind after schema changes — no one checks `$indexStats`, so the old indexes quietly cost writes forever.

## Correct

Replace single-field-per-field sprawl with a small set of compound indexes aligned to real query patterns (see [index-compound-esr](index-compound-esr.md)):

```javascript
db.products.createIndex({ sku: 1 }, { unique: true });
db.products.createIndex({ category: 1, price: -1 });
db.products.createIndex({ category: 1, brand: 1, rating: -1 });
```

Review usage monthly (or before a release) and drop indexes that aren't pulling their weight:

```javascript
db.products.aggregate([
  { $indexStats: {} },
  { $project: { name: 1, "accesses.ops": 1, "accesses.since": 1 } },
  { $sort: { "accesses.ops": 1 } }
]);
// Indexes with 0 ops (and a "since" date older than your typical traffic cycle)
// are safe to drop.

db.products.dropIndex("old_unused_index_name");
```

Budget guidelines:

- Aim for **5–15 indexes per collection**.
- Prefer a compound index that serves 3 query shapes over 3 single-field indexes.
- Never pre-create "maybe useful" indexes in production — create them when you see a query pattern in explain that justifies the cost.
- Track index count per collection in your CI or a simple script so a new index is a conscious decision.

## References

- [`$indexStats`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/)
- `query-optimizer/references/core-indexing-principles.md` — indexing anti-patterns
