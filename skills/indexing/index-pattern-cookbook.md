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

### 3. Equality + Range

```javascript
db.orders.find({ status: "open", total: { $gt: 100 } });
db.orders.createIndex({ status: 1, total: 1 });   // equality first, range last
```

### 4. Range + Sort (sort on same field as range)

```javascript
db.orders.find({ createdAt: { $gte: ISODate("2024-01-01") } }).sort({ createdAt: -1 });
db.orders.createIndex({ createdAt: -1 });        // one field serves both
```

### 5. Range + Sort (sort on different field)

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

### 6. Equality + Sort + Range

```javascript
db.orders.find({ status: "shipped", region: "US", total: { $gt: 100 } })
         .sort({ createdAt: -1 });
db.orders.createIndex({ status: 1, region: 1, createdAt: -1, total: 1 });
//                     └── equality ──┘        └ sort ┘     └ range ┘
```

### 7. Array containment

```javascript
db.products.find({ tags: "wireless" });
db.products.createIndex({ tags: 1 });                 // multikey index

// With a scalar filter — put the array field last (only one array per compound):
db.products.find({ category: "Electronics", tags: "wireless" })
           .sort({ price: 1 });
db.products.createIndex({ category: 1, price: 1, tags: 1 });
```

### 8. Nested-field filter

```javascript
db.users.find({ "address.city": "Seattle" });
db.users.createIndex({ "address.city": 1 });
```

### 9. Uniqueness constraint + lookup

```javascript
db.users.createIndex({ email: 1 }, { unique: true });  // lookup + enforcement
```

### 10. Optional-field uniqueness

```javascript
// Only enforce uniqueness on documents that actually have phone
db.users.createIndex({ phone: 1 }, { unique: true, sparse: true });
```

### 11. Filtered subset ("only active / published rows")

```javascript
db.products.createIndex(
  { name: 1 },
  { partialFilterExpression: { published: true } }
);
// Queries must include the filter condition to hit the index:
db.products.find({ name: "Laptop Pro", published: true });
```

### 12. Case-insensitive lookup

```javascript
db.users.createIndex(
  { username: 1 },
  { collation: { locale: "en", strength: 2 } }   // case-insensitive
);
db.users.find({ username: "ALICE" })
        .collation({ locale: "en", strength: 2 });  // must match index collation
```

### 13. Geospatial

```javascript
db.stores.createIndex({ category: 1, location: "2dsphere" });
db.stores.find({
  category: "coffee",
  location: { $near: { $geometry: { type: "Point", coordinates: [lng, lat] }, $maxDistance: 5000 } }
});
```
See [index-2dsphere-geospatial](index-2dsphere-geospatial.md).

### 14. Full-text (keyword) search

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

### 15. TTL / self-expiring documents

```javascript
db.sessions.createIndex({ expiresAt: 1 }, { expireAfterSeconds: 0 });
// Documents removed ~60s after expiresAt passes (see index-ttl-expiry).
```

### 16. Vector (similarity) search

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
