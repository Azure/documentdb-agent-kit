# index-text-prefer-textsearch

**Category:** Indexing · **Priority:** HIGH

## Why it matters

Community MongoDB tutorials routinely show `createIndex({ field: "text" })` + `$text` for keyword search. On **Azure DocumentDB**, the first-class full-text search path is a dedicated **search index created via `createSearchIndexes`** and queried through the **`$search` aggregation stage** — not the legacy `$text` operator. The search index lives in its own namespace (it isn't created by `createIndex`) and supports BM25 scoring, custom analyzers, fuzzy matching (`maxEdits`), phrase search (`slop`), prefix matching via `edgeGram`, and a per-result `searchScore` via `$meta`.

Don't reach for `"text"`-type indexes by reflex. On DocumentDB, the idiomatic path is `createSearchIndexes` + `$search`.

## Incorrect

Community-style text index + `$text` operator:

```javascript
db.products.createIndex({ name: "text", description: "text" });

db.products.find({ $text: { $search: "wireless headphones" } });
```

This is MongoDB community syntax. It does not support typo tolerance, phrase search, custom analyzers, or hybrid (BM25 + vector) retrieval. Use the DocumentDB-native path instead.

Also wrong — trying to create the search index via `createIndexes` with a `"textSearch"` key (a common confusion from older docs):

```javascript
// ❌ The DocumentDB search engine does not consume this shape
db.runCommand({
  createIndexes: "products",
  indexes: [{ key: { description: "textSearch" }, name: "description_textSearch" }]
});
```

## Correct

Use `createSearchIndexes` + `$search`:

```javascript
db.runCommand({
  createSearchIndexes: "products",
  indexes: [
    {
      name: "idx_description_fts",
      definition: {
        mappings: {
          dynamic: false,
          fields: { description: { type: "string" } }
        }
      }
    }
  ]
});

db.products.aggregate([
  {
    $search: {
      index: "idx_description_fts",
      text: { query: "wireless headphones", path: "description" }
    }
  },
  { $limit: 10 },
  { $project: { _id: 0, name: 1, description: 1, score: { $meta: "searchScore" } } }
]);
```

For detailed operator coverage — `text`, `phrase` (with `slop`), `fuzzy` (with `maxEdits`), custom analyzers for prefix matching, and BM25 + vector hybrid retrieval via RRF — see the `full-text-search/` rules:

- [fts-create-search-index](../full-text-search/fts-create-search-index.md)
- [fts-basic-search](../full-text-search/fts-basic-search.md)
- [fts-fuzzy-search](../full-text-search/fts-fuzzy-search.md)
- [fts-phrase-search](../full-text-search/fts-phrase-search.md)
- [fts-custom-analyzers](../full-text-search/fts-custom-analyzers.md)
- [fts-path-hierarchy](../full-text-search/fts-path-hierarchy.md)
- [fts-multifield-index](../full-text-search/fts-multifield-index.md)
- [fts-hybrid-search](../full-text-search/fts-hybrid-search.md)

## References

- Azure DocumentDB full-text search (in this kit, `full-text-search/` rules)
- [`$search` aggregation stage on Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/)

