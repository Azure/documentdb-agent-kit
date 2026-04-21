# index-text-prefer-textsearch

**Category:** Indexing · **Priority:** HIGH

## Why it matters

Community MongoDB tutorials routinely show `createIndex({ field: "text" })` + `$text` for keyword search. On **Azure DocumentDB**, the first-class full-text search path is the dedicated **`textSearch` index type** queried through the **`$search` aggregation stage** — not the legacy `$text` operator. `textSearch` gives you BM25 scoring, fuzzy matching (`maxEdits`), phrase search (`slop`), and a per-result `searchScore` via `$meta`.

Don't reach for `"text"`-type indexes by reflex. On DocumentDB, the idiomatic index is `textSearch`, and the query path is `$search`.

## Incorrect

Community-style text index + `$text` operator:

```javascript
db.products.createIndex({ name: "text", description: "text" });

db.products.find({ $text: { $search: "wireless headphones" } });
```

This is MongoDB community syntax. Pick the DocumentDB-native path instead — it supports typo tolerance, phrase search, and hybrid (BM25 + vector) retrieval, none of which `$text` handles.

## Correct

Use a `textSearch` index, queried via `$search`:

```javascript
db.runCommand({
  createIndexes: "products",
  indexes: [
    { key: { description: "textSearch" }, name: "description_textSearch" }
  ]
});

db.products.aggregate([
  { $search: { text: { query: "wireless headphones", path: "description" }, count: 10 } },
  { $project: { name: 1, description: 1, score: { $meta: "searchScore" } } }
]);
```

For detailed operator coverage — `text`, `phrase` (with `slop`), `fuzzy` (with `maxEdits`), and BM25 + vector hybrid retrieval via RRF — see the `full-text-search/` rules:

- [fts-create-textsearch-index](../full-text-search/fts-create-textsearch-index.md)
- [fts-basic-search](../full-text-search/fts-basic-search.md)
- [fts-fuzzy-search](../full-text-search/fts-fuzzy-search.md)
- [fts-phrase-search](../full-text-search/fts-phrase-search.md)
- [fts-hybrid-search](../full-text-search/fts-hybrid-search.md)

## References

- Azure DocumentDB full-text search (in this kit, `full-text-search/` rules)
- [`$search` aggregation stage on Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/)
