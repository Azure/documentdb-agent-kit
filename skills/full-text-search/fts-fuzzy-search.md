# fts-fuzzy-search

**Category:** Full-Text Search · **Priority:** HIGH

## Why it matters

Users mistype. Fuzzy search lets `$search` match terms within a bounded **edit distance (Levenshtein)** of the query, so `"s0me"` can still find `"some"`. On Azure DocumentDB this is expressed by adding a `fuzzy` object to the `text` operator with `maxEdits`.

Use fuzzy search for:
- Search-as-you-type UIs and misspelling tolerance.
- User-facing product/catalog search.
- Log/entity search where noise is common.

Do **not** default every search to fuzzy — higher `maxEdits` significantly broadens the candidate set, hurts precision, and costs latency. Keep `maxEdits` small.

## Incorrect

Raising `maxEdits` too high to "just get more matches":

```javascript
// Edit distance 3 on short tokens matches almost everything — noisy and slow
db.mongo_bm25_collection.aggregate([
  { $search: { text: { query: "s0me", path: "a", fuzzy: { maxEdits: 3 } }, count: 5 } }
]);
```

Or using `$regex` with `.*` wildcards to simulate fuzziness:

```javascript
db.mongo_bm25_collection.find({ a: { $regex: ".*s.me.*" } }); // COLLSCAN, no BM25 ranking
```

## Correct

```javascript
db.mongo_bm25_collection.aggregate([
  {
    $search: {
      text: {
        query: "s0me",
        path: "a",
        fuzzy: { maxEdits: 1 }
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

Tuning:
- `maxEdits: 1` — typical for short words; high precision.
- `maxEdits: 2` — better recall for longer words at the cost of noise.
- Combine with a minimum `rank` threshold or a `$limit` after `$sort: { rank: -1 }` to cut low-relevance hits.

## References

- [Azure DocumentDB — full-text search (fuzzy)](https://learn.microsoft.com/azure/documentdb/)
