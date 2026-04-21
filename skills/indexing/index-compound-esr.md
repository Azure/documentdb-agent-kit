# index-compound-esr

**Category:** Indexing · **Priority:** CRITICAL

## Why it matters

A compound index over the right columns, in the right order, can serve **multiple** query shapes at once — and eliminates the expensive blocking in-memory sort that appears when the sort field isn't in the index prefix. The standard recipe is the **ESR rule**: order fields as **Equality → Sort → Range**.

Prefer **one well-designed compound index** over many overlapping single-field indexes. MongoDB's index-intersection planner can combine two single-field indexes, but the result is almost always slower than a purpose-built compound index and confuses the planner.

Azure DocumentDB allows up to **32 fields** in a compound index, but any compound index beyond 3–4 fields is almost always a sign the query shape is wrong.

## Index-prefix rule

A compound index serves any query whose fields are a **left-to-right prefix** of the index. Sort fields must also match the prefix position. Given:

```javascript
db.products.createIndex({ category: 1, brand: 1, price: 1 });
```

| Query | Uses index? |
|---|---|
| `find({ category })` | ✅ prefix `{category}` |
| `find({ category, brand })` | ✅ prefix `{category, brand}` |
| `find({ category, brand, price: {$lte: 500} })` | ✅ full index |
| `find({ brand })` | ❌ skips `category` |
| `find({ price: {$lte: 500} })` | ❌ skips `category, brand` |
| `find({ category }).sort({ price: -1 })` | ⚠️ sort skips `brand` — blocking SORT stage |

Design the index to match the **most-common** query's prefix; shorter-prefix queries come along for free.

## Incorrect

Single-field indexes that can't serve a compound query shape:

```javascript
db.orders.createIndex({ status: 1 });
db.orders.createIndex({ createdAt: -1 });

db.orders.find({ status: "open" }).sort({ createdAt: -1 });
// explain: IXSCAN on status_1, then blocking SORT stage
// totalDocsExamined >> nReturned
```

Putting a range field before a sort field in a compound index:

```javascript
db.orders.createIndex({ total: 1, createdAt: -1 });   // range before sort

db.orders.find({ total: { $gt: 100 } }).sort({ createdAt: -1 });
// Index satisfies the range, but cannot serve the sort — blocking SORT again.
```

## Correct

Apply ESR: **Equality first, then Sort, then Range.**

```javascript
db.orders.createIndex({ status: 1, createdAt: -1, total: 1 });
//                     └─ equality ─┘  └─ sort ─┘  └ range ┘

db.orders.find({ status: "open", total: { $gt: 100 } })
         .sort({ createdAt: -1 })
         .explain("executionStats");
// Expect: IXSCAN, no SORT stage, keysExamined ≈ docsExamined ≈ nReturned
```

One compound index can serve many query shapes that share its prefix:

```javascript
db.orders.createIndex({ customerId: 1, status: 1, createdAt: -1 });

// All of these can use it (index prefix rule):
db.orders.find({ customerId: "c1" });
db.orders.find({ customerId: "c1", status: "open" });
db.orders.find({ customerId: "c1", status: "open" }).sort({ createdAt: -1 });
// But NOT: db.orders.find({ status: "open" })  — no customerId, breaks prefix
```

**Sort direction:** for a single sort field, direction doesn't matter (reverse scan). For multi-field sorts, the index direction must match the sort direction (or be its exact inverse): `{ a: 1, b: -1 }` serves `sort({ a: 1, b: -1 })` and `sort({ a: -1, b: 1 })` — not `sort({ a: 1, b: 1 })`.

## References

- [MongoDB ESR rule](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-rule/)
- [MongoDB compound indexes](https://www.mongodb.com/docs/manual/core/index-compound/)
- Companion: [query-optimizer/references/core-indexing-principles.md](../query-optimizer/references/core-indexing-principles.md)
