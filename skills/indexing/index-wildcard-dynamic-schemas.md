# index-wildcard-dynamic-schemas

**Category:** Indexing · **Priority:** MEDIUM

## Why it matters

A **wildcard index** (`{ "path.$**": 1 }`) indexes every field under a subtree whose field names you don't know at design time — typical for user-defined attributes, feature flags, or CMS metadata blobs. It's a powerful tool for truly dynamic schemas, but it's also the most expensive general-purpose index: every field, in every document, under the matched path gets indexed on every write.

Before reaching for a wildcard index, ask: *"Could I model this as a known set of fields, or as key/value pairs with the attribute name as a value?"* (see `data-modeling/`). Most of the time, yes — and a focused compound index will be cheaper than a wildcard.

## Incorrect

Rooting the wildcard at the document top:

```javascript
// Indexes EVERY scalar field in EVERY document under this collection.
db.products.createIndex({ "$**": 1 });
// Huge index, massive write amplification, obscures planner choices.
```

Using a wildcard where a normal compound index would do:

```javascript
// Query always touches { category: ..., price: ... }
db.products.createIndex({ "$**": 1 });
// A plain compound index { category: 1, price: 1 } would be orders of
// magnitude cheaper and give a better plan.
```

## Correct

Scope the wildcard to the subtree that's actually dynamic:

```javascript
// Only the "attributes" subdocument has unknown field names.
db.products.createIndex({ "attributes.$**": 1 });

db.products.find({ "attributes.color": "red" });
db.products.find({ "attributes.material": "steel" });
```

Limit which fields participate with `wildcardProjection`:

```javascript
db.products.createIndex(
  { "$**": 1 },
  { wildcardProjection: { attributes: 1, specs: 1 } }
);
```

Rules of thumb:

- Prefer a named compound index whenever the query fields are known.
- Prefer the **attribute pattern** (store attributes as `[{ k, v }]` with a compound index on `{ "attrs.k": 1, "attrs.v": 1 }`) when the set of attributes is large but queries still target them by name.
- Only use `"$**"` at the root for small, read-heavy collections with genuinely unknown query shapes.

## References

- [MongoDB wildcard indexes](https://www.mongodb.com/docs/manual/core/index-wildcard/)
- `data-modeling/` — attribute pattern discussion
