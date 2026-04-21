# fts-basic-search

**Category:** Full-Text Search · **Priority:** HIGH

## Why it matters

The `$search` aggregation stage with a `text` operator runs a **BM25**-scored keyword search against a `textSearch`-indexed field. Use it whenever you want tokenized, ranked keyword matching — not a substring `$regex`, which is unranked and forces a collection scan on large data.

Always:
- Project `{ $meta: "searchScore" }` so callers can rank, threshold, or rerank results.
- Pass `count` inside `$search` to cap the number of candidates evaluated.
- Put the `$search` stage first; it uses the index and narrows the pipeline early.

## Incorrect

Substring regex for keyword search — unranked, `COLLSCAN`, case-sensitive footguns:

```javascript
db.mongo_bm25_collection.find({ a: { $regex: "good word", $options: "i" } });
```

Or `$search` without projecting the score, leaving the caller no way to rank:

```javascript
db.mongo_bm25_collection.aggregate([
  { $search: { text: { query: "good word", path: "a" } } }
  // no score projection
]);
```

## Correct

```javascript
db.mongo_bm25_collection.aggregate([
  {
    $search: {
      text: {
        query: "good word",
        path: "a"
      },
      count: 5
    }
  },
  {
    $project: {
      a: 1,
      rank: { $meta: "searchScore" }
    }
  }
]);
```

Tips:
- Sort by `rank` descending when you need stable top-N output:
  ```javascript
  { $sort: { rank: -1 } }
  ```
- For multi-field search, use an array `path`: `path: ["title", "body"]` (ensure each field has a `textSearch` index).
- Apply additional equality/range filters with a later `$match`; keep the `$search` stage pure so it can leverage the index fully.

## References

- [Azure DocumentDB — full-text search on `$search`](https://learn.microsoft.com/azure/documentdb/)
