# fts-phrase-search

**Category:** Full-Text Search · **Priority:** HIGH

## Why it matters

Phrase search matches query terms that appear **together in order**, with an optional `slop` tolerance for intervening tokens. Unlike a plain `text` query (which matches tokens anywhere in any order), `phrase` enforces proximity — critical for multi-word product names, quoted strings, or error messages where ordering matters.

Use `phrase` on Azure DocumentDB when:

- The user enters a quoted phrase (`"bracket controller"`).
- You need title / entity / error-string matching where word order is meaningful.
- Plain `text` returns too much noise because tokens are common individually but rare together.

## Incorrect

Using `text` when you actually need ordered proximity — high recall, low precision:

```javascript
db.products_10M.aggregate([
  { $search: {
      index: "idx_title_standard",
      text: { query: "bracket controller", path: "title" }
  }},
  { $limit: 20 }
]);
// Matches "controller for bracket", "bracket without controller", etc. —
// not what the user meant.
```

Or concatenating with regex to hack phrase behaviour and losing BM25 ranking:

```javascript
db.products_10M.find({ title: { $regex: "bracket.*controller" } });
```

## Correct

```javascript
db.products_10M.aggregate([
  {
    $search: {
      index: "idx_title_standard",
      phrase: {
        query: "bracket controller",
        path: "title",
        slop: 3
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

`slop` guidance:

- `slop: 0` — strict adjacency. Matches `"bracket controller"` but not `"bracket for controller"`.
- `slop: 1` — allows one intervening token. Matches `"bracket for controller"`.
- `slop: 3` — broader proximity; useful for titles with adjectives or articles between the terms.
- **Don't combine `phrase` with `fuzzy`** — they're separate operators. If you need both typo tolerance and ordering, run two queries and fuse the results.

Combine `phrase` with equality/range filters in a later `$match` stage, never inside the `$search`.

## References

- [Azure DocumentDB — full-text search (phrase)](https://learn.microsoft.com/azure/documentdb/)
