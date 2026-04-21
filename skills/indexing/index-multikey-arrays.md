# index-multikey-arrays

**Category:** Indexing · **Priority:** HIGH

## Why it matters

When you index a field whose value is an array, Azure DocumentDB creates a **multikey index** — one index entry per array element, per document. This is the only way to efficiently query array contents (tags, roles, categories, embedded-document arrays).

Two rules shape almost every multikey-index decision:

1. **Parallel-array restriction** — a compound index may include **at most one** array field. `{ tags: 1, categories: 1 }` where both are arrays fails with "cannot index parallel arrays".
2. **No covered queries** — multikey indexes cannot cover a query (the planner always fetches the document), so don't bother trying to structure one for that purpose.

## Incorrect

Trying to index two array fields together:

```javascript
db.products.createIndex({ tags: 1, categories: 1 });
// Error: cannot index parallel arrays [categories] [tags]
```

Creating one giant multikey index on an unbounded array:

```javascript
// Each product can have hundreds of tags — each one produces an index entry.
db.products.createIndex({ tags: 1 });
// Writes slow down linearly with array length; index grows fast.
```

Using `$all` when `$in` is what you actually want:

```javascript
db.products.find({ tags: { $all: ["wireless", "bluetooth"] } });
// Requires BOTH tags. If the user wanted "either", this silently returns fewer results.
```

## Correct

Index one array field per compound index; fan out with multiple indexes if you truly need both:

```javascript
db.products.createIndex({ tags: 1, price: 1 });        // tags = array, price = scalar
db.products.createIndex({ categories: 1, price: 1 });  // separate index for the other array
```

Use `$elemMatch` when you need multiple conditions against the **same** array element:

```javascript
// Array of embedded docs
{ _id: 1, reviews: [{ user: "a", rating: 5 }, { user: "b", rating: 2 }] }

// Wrong: matches any doc where some review has rating >= 4 AND some review is by "b"
db.products.find({ "reviews.rating": { $gte: 4 }, "reviews.user": "b" });

// Right: all conditions must match the SAME review element
db.products.find({
  reviews: { $elemMatch: { rating: { $gte: 4 }, user: "b" } }
});
db.products.createIndex({ "reviews.rating": 1, "reviews.user": 1 });
```

Keep arrays bounded — a 100-element `tags` array means 100 index entries per document, on every write. Cap at a sensible maximum or move to a child collection (see `data-modeling/model-embed-vs-reference`).

Verify with explain:

```javascript
db.products.find({ tags: "wireless" }).explain("executionStats");
// Expect: "isMultiKey": true, "stage": "IXSCAN", indexName: "tags_1"
```

## References

- [MongoDB multikey indexes](https://www.mongodb.com/docs/manual/core/index-multikey/)
- [`$elemMatch`](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/)
