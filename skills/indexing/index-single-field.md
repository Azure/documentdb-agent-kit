# index-single-field

**Category:** Indexing · **Priority:** HIGH

## Why it matters

A single-field index is the simplest useful index — one field, one traversable B-tree. Get this right first: most "slow query" problems are a single missing single-field index, not an exotic index type. For single-field indexes, direction (`1` vs `-1`) is largely cosmetic — Azure DocumentDB can traverse a single-field index in either direction, so `createIndex({ price: 1 })` serves both `.sort({ price: 1 })` and `.sort({ price: -1 })`.

Azure DocumentDB allows up to **64 single-field indexes per collection** by default (extendable to 300 on request). Only `_id` is created automatically.

## When to reach for a single-field index

- The query filters or sorts by exactly one field.
- The field has **high cardinality** (many unique values) — an index on a boolean or a handful of statuses rarely pays off on its own.
- You need `unique`, `sparse`, or `partialFilterExpression` on that field.
- The field is a natural key (email, username, SKU) — add `{ unique: true }`.

For anything else (multi-field filters, filter + sort, filter + range), jump straight to a compound index — see [index-compound-esr](index-compound-esr.md).

## Incorrect

Creating many overlapping single-field indexes when compound indexes would serve the real query patterns:

```javascript
db.products.createIndex({ category: 1 });
db.products.createIndex({ price: 1 });
db.products.createIndex({ rating: 1 });
db.products.createIndex({ brand: 1 });
// Query that actually runs:
db.products.find({ category: "Electronics", brand: "Acme" })
           .sort({ price: -1 });
// None of these indexes fully supports this query — engine either
// intersects indexes (rarely optimal) or falls back to COLLSCAN.
```

Indexing a low-cardinality boolean on its own:

```javascript
db.products.createIndex({ inStock: 1 });   // only 2 values; half the collection matches
```

## Correct

Add `unique` / `sparse` / `partial` where they apply:

```javascript
// Natural unique key
db.users.createIndex({ email: 1 }, { unique: true });

// Optional unique field — only enforce uniqueness on documents that have it
db.users.createIndex({ phone: 1 }, { unique: true, sparse: true });

// Partial index: only index "published" rows the app actually queries
db.products.createIndex(
  { name: 1 },
  { partialFilterExpression: { published: true } }
);
```

Index nested fields with dot notation:

```javascript
db.users.createIndex({ "address.city": 1 });
db.users.find({ "address.city": "Seattle" }).explain("executionStats");
// Expect: IXSCAN on address.city_1
```

Match the query's collation at index-creation time, or the index won't be used:

```javascript
db.users.createIndex(
  { username: 1 },
  { collation: { locale: "en", strength: 2 } }   // case-insensitive
);

db.users.find({ username: "ALICE" })
        .collation({ locale: "en", strength: 2 });
```

## References

- [Azure DocumentDB — MQL compatibility](https://learn.microsoft.com/azure/documentdb/compatibility-query-language)
- MongoDB docs: [Single field indexes](https://www.mongodb.com/docs/manual/core/index-single/), [Partial indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
