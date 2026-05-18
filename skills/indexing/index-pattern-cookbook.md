# index-pattern-cookbook

**Category:** Indexing · **Priority:** HIGH

## Why it matters

Most queries fall into a handful of shapes. Matching the query shape to a good index shape is mechanical once you recognize the pattern. Use this as a lookup table — find the row that matches your query, copy the index shape, adapt field names.

All shapes below follow the **ESR rule** (Equality → Sort → Range). For deeper reasoning, see [index-compound-esr](index-compound-esr.md) and `query-optimizer/references/core-indexing-principles.md`.

## Pattern → index cookbook

### 1. Equality + Sort

```javascript
// Query
db.orders.find({ status: "shipped" }).sort({ createdAt: -1 });

// Index
db.orders.createIndex({ status: 1, createdAt: -1 });
```

### 2. Multi-equality

```javascript
db.orders.find({ status: "shipped", region: "US" });
db.orders.createIndex({ status: 1, region: 1 });

// If you usually add a sort:
db.orders.find({ status: "shipped", region: "US" }).sort({ createdAt: -1 });
db.orders.createIndex({ status: 1, region: 1, createdAt: -1 });
```

**Selectivity ordering:** Among multiple `$eq` filters, put the field with the fewest matching documents first. This narrows the candidate set earlier and reduces work for subsequent filters.

```javascript
// Collection: 1M orders, 10 customers (100K each), 2 statuses (500K each)
db.orders.find({ customerId: "cust1", status: "active" });

// ✅ Correct: customerId first (100K candidates → filters to ~50K)
db.orders.createIndex({ customerId: 1, status: 1 });

// ❌ Wrong: status first (500K candidates → filters to ~50K)
db.orders.createIndex({ status: 1, customerId: 1 });
```

General selectivity guidance (typical defaults — actual cardinality depends on the collection, so sanity-check with a quick distinct-count):
- **High** (few matches): `userId`, `orderId`, `email`, `SKU`
- **Medium**: `customerId`, `productId`
- **Low** (many matches): `status`, `category`, `country`

### 3. Mixed equality — `$eq` before `$in`

When some filters are exact equality (`$eq`) and others are `$in`, put exact equality fields first. `$in` behaves like a bounded multi-equality / range; under ESR, place it after pure equality and (when present) the sort field.

```javascript
db.orders.find({
  customerId: "cust123",                         // exact equality
  status: { $in: ["pending", "processing"] }     // $in — place after $eq
}).sort({ createdAt: -1 });

// ✅ Correct: $eq → sort → $in
db.orders.createIndex({ customerId: 1, createdAt: -1, status: 1 });

// ❌ Wrong: $in first
db.orders.createIndex({ status: 1, customerId: 1, createdAt: -1 });
```

### 4. Equality + Range

```javascript
db.orders.find({ status: "open", total: { $gt: 100 } });
db.orders.createIndex({ status: 1, total: 1 });   // equality first, range last
```

### 5. Range + Sort (sort on same field as range)

```javascript
db.orders.find({ createdAt: { $gte: ISODate("2024-01-01") } }).sort({ createdAt: -1 });
db.orders.createIndex({ createdAt: -1 });        // one field serves both
```

### 6. Range + Sort (sort on different field)

```javascript
// This shape cannot avoid a SORT without careful design.
db.orders.find({ total: { $gt: 100 } }).sort({ createdAt: -1 });

// Best option: if the result set is small, sort is cheap.
db.orders.createIndex({ total: 1 });

// Better option if volumes are large: add a bucketed equality field (e.g. status,
// tier, region) and fall back to equality+sort pattern (#1).
db.orders.find({ status: "open", total: { $gt: 100 } }).sort({ createdAt: -1 });
db.orders.createIndex({ status: 1, createdAt: -1, total: 1 });  // ESR
```

### 7. Equality + Sort + Range

```javascript
db.orders.find({ status: "shipped", region: "US", total: { $gt: 100 } })
         .sort({ createdAt: -1 });
db.orders.createIndex({ status: 1, region: 1, createdAt: -1, total: 1 });
//                     └── equality ──┘        └ sort ┘     └ range ┘
```

### 8. Array containment

```javascript
db.products.find({ tags: "wireless" });
db.products.createIndex({ tags: 1 });                 // multikey index

// With a scalar filter — put the array field last (only one array per compound):
db.products.find({ category: "Electronics", tags: "wireless" })
           .sort({ price: 1 });
db.products.createIndex({ category: 1, price: 1, tags: 1 });
```

**Partial indexes on array fields.** When an array field can grow large, two distinct patterns use a `partialFilterExpression` for different reasons:

*Multikey reduction* — restrict the multikey index on the array itself to the subset of documents you actually query, so writes to documents outside the subset don't pay the per-element indexing cost.

```javascript
// orders.items can have 100+ elements — only multikey-index open orders.
db.orders.createIndex(
  { items: 1 },
  {
    partialFilterExpression: { status: "open" },
    name: "idx_items_open"
  }
);
// ✅ Served — query filter includes status:"open" (matches the partial expression)
db.orders.find({ status: "open", items: "SKU-123" });
// ❌ Not served — without status:"open", planner can't use the partial index (COLLSCAN)
db.orders.find({ items: "SKU-123" });
```

*Empty-array enumeration* — find documents whose array is empty without paying the cost of `$size: 0` (which can't use a regular multikey index and forces a scan). A partial index keyed on `_id` and filtered to the empty-array predicate gives you a cheap, direct enumeration.

```javascript
// Fast lookup for "orders with no items" without scanning the collection.
db.orders.createIndex(
  { _id: 1 },
  {
    partialFilterExpression: { items: { $eq: [] } },
    name: "idx_empty_orders"
  }
);
// ✅ Served — query filter matches the partial expression exactly
db.orders.find({ items: { $eq: [] } });
```

### 9. Nested-field filter

```javascript
db.users.find({ "address.city": "Seattle" });
db.users.createIndex({ "address.city": 1 });
```

### 10. Uniqueness constraint + lookup

```javascript
db.users.createIndex({ email: 1 }, { unique: true });  // lookup + enforcement
```

### 11. Optional-field uniqueness

```javascript
// Only enforce uniqueness on documents that actually have phone
db.users.createIndex({ phone: 1 }, { unique: true, sparse: true });
```

### 12. Filtered subset ("only active / published rows")

```javascript
db.products.createIndex(
  { name: 1 },
  { partialFilterExpression: { published: true } }
);
// Queries must include the filter condition to hit the index:
db.products.find({ name: "Laptop Pro", published: true });
```

### 13. Case-insensitive lookup

```javascript
db.users.createIndex(
  { username: 1 },
  { collation: { locale: "en", strength: 2 } }   // case-insensitive
);
db.users.find({ username: "ALICE" })
        .collation({ locale: "en", strength: 2 });  // must match index collation
```

### 14. Geospatial

```javascript
db.stores.createIndex({ category: 1, location: "2dsphere" });
db.stores.find({
  category: "coffee",
  location: { $near: { $geometry: { type: "Point", coordinates: [lng, lat] }, $maxDistance: 5000 } }
});
```
See [index-2dsphere-geospatial](index-2dsphere-geospatial.md).

### 15. Full-text (keyword) search

Prefer Azure DocumentDB's dedicated search index (`createSearchIndexes` + `$search`) — see [index-text-prefer-textsearch](index-text-prefer-textsearch.md) and the `full-text-search/` rules.

```javascript
db.runCommand({
  createSearchIndexes: "products",
  indexes: [{
    name: "idx_description_fts",
    definition: {
      mappings: {
        dynamic: false,
        fields: { description: { type: "string" } }
      }
    }
  }]
});

db.products.aggregate([
  { $search: {
      index: "idx_description_fts",
      text: { query: "wireless headphones", path: "description" }
  }},
  { $limit: 10 },
  { $project: { name: 1, score: { $meta: "searchScore" } } }
]);
```

### 16. TTL / self-expiring documents

```javascript
db.sessions.createIndex({ expiresAt: 1 }, { expireAfterSeconds: 0 });
// Documents removed ~60s after expiresAt passes (see index-ttl-expiry).
```

### 17. Vector (similarity) search

See the `vector-search/` rules:
- [vector-choose-index-type](../vector-search/vector-choose-index-type.md)
- [vector-create-diskann-index](../vector-search/vector-create-diskann-index.md)
- [vector-knn-query](../vector-search/vector-knn-query.md)

## Always verify

Run `explain("executionStats")` after creating the index and check:

- Winning plan starts with `IXSCAN`, not `COLLSCAN`.
- No blocking `SORT` stage.
- `keysExamined ≈ docsExamined ≈ nReturned`.

See `query-optimizer/references/core-indexing-principles.md` for the full diagnostic ratio table.

## References

- `query-optimizer/references/core-indexing-principles.md`
- [MongoDB compound indexes](https://www.mongodb.com/docs/manual/core/index-compound/)
