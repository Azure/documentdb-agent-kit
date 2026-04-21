# fts-phrase-search

**Category:** Full-Text Search · **Priority:** HIGH

## Why it matters

Phrase search matches query terms that appear **together in order**, with an optional `slop` tolerance for intervening tokens. Unlike a plain `text` query (which matches tokens anywhere in any order), `phrase` enforces proximity — critical for multi-word product names, quotes, or error messages where ordering matters.

Use `phrase` on Azure DocumentDB when:
- The user enters a quoted phrase (`"some good"`).
- You need title / entity / error-string matching where word order is meaningful.
- Plain `text` returns too much noise because tokens are common individually but rare together.

## Incorrect

Using `text` when you actually need ordered proximity — high recall, low precision:

```javascript
db.mongo_bm25_collection.aggregate([
  { $search: { text: { query: "some good", path: "a" }, count: 5 } }
  // Matches "some word good", "good word some", etc. — not what the user meant.
]);
```

Or concatenating with regex to hack phrase behavior, losing BM25 ranking:

```javascript
db.mongo_bm25_collection.find({ a: { $regex: "some.*good" } });
```

## Correct

```javascript
db.mongo_bm25_collection.aggregate([
  {
    $search: {
      phrase: {
        query: "some good",
        path: "a",
        slop: 1
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

`slop` guidance:
- `slop: 0` — exact adjacency, strictest.
- `slop: 1` — allows one intervening token (e.g., `"some word good"` matches `"some good"`).
- `slop: 2+` — broader proximity; use carefully.

Combine `phrase` with equality/range filters in a later `$match` stage, and sort by `rank` desc to return the best matches first.

## References

- [Azure DocumentDB — full-text search (phrase)](https://learn.microsoft.com/azure/documentdb/)
