# fts-create-textsearch-index

**Category:** Full-Text Search · **Priority:** HIGH

## Why it matters

Azure DocumentDB provides native BM25-based full-text search via a dedicated **`textSearch`** index type, queried through the `$search` aggregation stage. Community MongoDB's `$text` operator and `"text"` index type are **not** the preferred path — use `textSearch` to get BM25 relevance scoring, fuzzy matching, and phrase queries with `slop`.

Without a `textSearch` index, `$search` queries cannot run on the target field.

## Incorrect

Relying on community MongoDB `$text`:

```javascript
db.mongo_bm25_collection.createIndex({ a: "text" });
db.mongo_bm25_collection.find({ $text: { $search: "good word" } });
```

Or trying to query with `$search` before creating the index:

```javascript
// No index on "a" — query will fail / return nothing useful
db.mongo_bm25_collection.aggregate([
  { $search: { text: { query: "good word", path: "a" } } }
]);
```

## Correct

Create a `textSearch` index with `runCommand({ createIndexes })`, then verify:

```javascript
db.createCollection("mongo_bm25_collection");

db.mongo_bm25_collection.insertMany([
  { _id: 1, a: "some sentence sentence", v: [1, 2, 3] },
  { _id: 2, a: "other sentence",         v: [1, 2.0, 4] },
  { _id: 4, a: "some word word",         v: [3, 2, 1] },
  { _id: 5, a: "other word",             v: [4, 2, 1] },
  { _id: 6, a: "some word good",         v: [3, 2, 1] }
]);

db.runCommand({
  createIndexes: "mongo_bm25_collection",
  indexes: [
    {
      key: { a: "textSearch" },
      name: "text_search_index"
    }
  ]
});

// Confirm
db.mongo_bm25_collection.getIndexes();
```

Guidelines:
- One `textSearch` index per text field you intend to query; name it descriptively.
- Create the index **before** ingesting large volumes, or rebuild after bulk load.
- Pair with a vector `cosmosSearch` index on the same collection to enable hybrid search (keyword + semantic).

## References

- [Azure DocumentDB overview](https://learn.microsoft.com/azure/documentdb/overview)
- [MQL compatibility](https://learn.microsoft.com/azure/documentdb/compatibility-query-language)
