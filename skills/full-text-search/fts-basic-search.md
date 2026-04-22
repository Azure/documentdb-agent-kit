# fts-basic-search

**Category:** Full-Text Search · **Priority:** HIGH

## Why it matters

The `$search` aggregation stage with the `text` operator runs a BM25-scored keyword search against a field covered by a search index created with `createSearchIndexes`. Use it instead of `$regex` for keyword lookup on large collections — regex forces a `COLLSCAN`, is unranked, and is case-sensitive without `/i`.

Always:

- Put `$search` **first** in the pipeline so it uses the index and narrows early.
- Pass `index: "<name>"` explicitly when the collection has more than one search index — the engine does not auto-pick.
- Use a downstream **`{ $limit: N }`** stage to cap results (there is no `count` / `limit` field inside `$search` in the Azure DocumentDB syntax).
- Project `score: { $meta: "searchScore" }` so callers can rank, threshold, or rerank.

## Incorrect

Substring `$regex` as a keyword search — unranked, `COLLSCAN`, and typo-intolerant:

```javascript
db.products_10M.find({ title: { $regex: "bracket", $options: "i" } });
```

`$search` without targeting an index, or trying to limit via a non-existent `count` field:

```javascript
db.products_10M.aggregate([
  { $search: { text: { query: "bracket", path: "title" }, count: 20 } }
  // ❌ `count` is not a valid $search field in DocumentDB; use a $limit stage
]);
```

## Correct

```javascript
db.products_10M.aggregate([
  {
    $search: {
      index: "idx_title_standard",
      text: {
        query: "bracket",
        path: "title"
      }
    }
  },
  { $limit: 20 },
  {
    $project: {
      _id: 0,
      title: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

Tips:

- **Sort implicitly via `$limit`.** `$search` returns results sorted by BM25 score descending — projection of `searchScore` lets the caller see the scores; add `{ $sort: { score: -1 } }` only when a later stage disturbs order.
- **Query one field at a time.** `path` takes a single string, matching the indexed field. For queries that should match any of several fields, see `fts-multifield-index`.
- **Apply extra filters after** `$search` with `$match`, not inside — e.g. `{ $match: { inStock: true } }` keeps the `$search` stage pure and index-friendly.
- **Pick the right analyzer at index time.** A plain `text` search against an `edgeGram`-indexed field is how prefix matching works (see `fts-custom-analyzers`); against a standard mapping it's BM25 on tokenized terms.

## References

- [Azure DocumentDB — full-text search](https://learn.microsoft.com/azure/documentdb/)
