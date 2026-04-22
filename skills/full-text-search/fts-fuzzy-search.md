# fts-fuzzy-search

**Category:** Full-Text Search · **Priority:** HIGH

## Why it matters

Real users mistype. Fuzzy search lets `$search` match terms within a bounded **edit distance (Levenshtein)** of the query, so `"bracXet"` still finds `"bracket"`. On Azure DocumentDB, fuzziness is a sub-object of the `text` operator with a `maxEdits` parameter.

Use fuzzy search for:

- Search-as-you-type UIs and misspelling tolerance.
- User-facing product / catalog search.
- Log or entity search where noise is common.

Do **not** default every search to fuzzy — higher `maxEdits` significantly broadens the candidate set, hurts precision, and increases latency. Keep `maxEdits` small and let exact matches rank naturally.

## Incorrect

Raising `maxEdits` beyond 2 — on short tokens this matches almost everything:

```javascript
db.products_10M.aggregate([
  { $search: {
      index: "idx_title_standard",
      text: { query: "bracXet", path: "title", fuzzy: { maxEdits: 3 } }
  }},
  { $limit: 20 }
]);
```

Or faking fuzziness with a wildcard `$regex` — `COLLSCAN`, no BM25 ranking, no real distance metric:

```javascript
db.products_10M.find({ title: { $regex: ".*br.cket.*" } });
```

## Correct

```javascript
db.products_10M.aggregate([
  {
    $search: {
      index: "idx_title_standard",
      text: {
        query: "bracXet",
        path: "title",
        fuzzy: { maxEdits: 1 }
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

Tuning:

- `maxEdits: 1` — typical for short words; high precision, good recall on one-character typos.
- `maxEdits: 2` — better recall for longer words at the cost of noise. Don't use on 3–4-character tokens.
- Short acronyms (≤3 chars) are better served by **edge n-gram** prefix matching than fuzzy — see `fts-custom-analyzers`.
- Combine with a minimum score threshold (`$match: { score: { $gte: ... } }`) or a fixed `$limit` to cut low-relevance hits.

## References

- [Azure DocumentDB — full-text search (fuzzy)](https://learn.microsoft.com/azure/documentdb/)
