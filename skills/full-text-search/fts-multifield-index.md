# fts-multifield-index

**Category:** Full-Text Search · **Priority:** MEDIUM

## Why it matters

When an app needs to search **several identifier-like fields** on the same collection — `serialNumber`, `basicNumber`, `customerCode`, `partNumber`, `lineNumber` — create **one search index that maps all of them**, not one index per field. A single index is cheaper to maintain, keeps storage bounded, and is reloaded atomically.

Each field keeps its own `analyzer` / `searchAnalyzer`, so the same index can simultaneously power prefix search on IDs and standard search on titles.

> **Version note.** The `$search` `compound` operator (`should` / `must` / `minimumShouldMatch` across multiple clauses) is **not yet supported** in current Azure DocumentDB. You still query one field at a time; the multi-field index exists so you don't have to juggle many separate indexes. Fan-out-and-merge at the application layer is the current workaround.

## Incorrect

Creating a separate search index per field — multiplies index-build time, storage, and write amplification:

```javascript
// ❌ One search index per field — don't do this
db.runCommand({ createSearchIndexes: "products_10M", indexes: [{ name: "idx_sn",  definition: { mappings: { fields: { serialNumber:  { type: "string" } } } } }] });
db.runCommand({ createSearchIndexes: "products_10M", indexes: [{ name: "idx_bn",  definition: { mappings: { fields: { basicNumber:   { type: "string" } } } } }] });
db.runCommand({ createSearchIndexes: "products_10M", indexes: [{ name: "idx_cc",  definition: { mappings: { fields: { customerCode:  { type: "string" } } } } }] });
// … etc
```

Trying to use `compound` to match any-field today — returns an error on current versions:

```javascript
// ❌ Not yet supported — tracks the feature, don't ship this
db.products_10M.aggregate([
  { $search: {
      index: "idx_identifiers_multifield",
      compound: {
        should: [
          { text: { query: "<Q>", path: "serialNumber"  } },
          { text: { query: "<Q>", path: "basicNumber"   } },
          { text: { query: "<Q>", path: "customerCode"  } },
          { text: { query: "<Q>", path: "partNumber"    } },
          { text: { query: "<Q>", path: "lineNumber"    } }
        ],
        minimumShouldMatch: 1
      }
  }}
]);
```

## Correct

One index, five fields, one analyzer pair reused:

```javascript
db.runCommand({
  createSearchIndexes: "products_10M",
  indexes: [
    {
      name: "idx_identifiers_multifield",
      definition: {
        analyzers: [
          {
            name: "kw_lc",
            tokenizer: { type: "keyword" },
            tokenFilters: [
              { type: "lowerCase" },
              { type: "asciiFolding" }
            ]
          },
          {
            name: "kw_lc_edge",
            tokenizer: { type: "keyword" },
            tokenFilters: [
              { type: "lowerCase" },
              { type: "asciiFolding" },
              { type: "edgeGram", minGram: 1, maxGram: 255 }
            ]
          }
        ],
        mappings: {
          dynamic: false,
          fields: {
            serialNumber: { type: "string", analyzer: "kw_lc_edge", searchAnalyzer: "kw_lc" },
            basicNumber:  { type: "string", analyzer: "kw_lc_edge", searchAnalyzer: "kw_lc" },
            customerCode: { type: "string", analyzer: "kw_lc_edge", searchAnalyzer: "kw_lc" },
            partNumber:   { type: "string", analyzer: "kw_lc_edge", searchAnalyzer: "kw_lc" },
            lineNumber:   { type: "string", analyzer: "kw_lc_edge", searchAnalyzer: "kw_lc" }
          }
        }
      }
    }
  ]
});
```

Query one field at a time (current-version pattern):

```javascript
db.products_10M.aggregate([
  {
    $search: {
      index: "idx_identifiers_multifield",
      text: { query: "Crm", path: "customerCode" }
    }
  },
  { $limit: 20 },
  {
    $project: {
      _id: 0,
      customerCode: 1,
      basicNumber: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

To search *any* of the five fields today, fan out in the application and merge — simple de-dupe by `_id`, keep the max score, sort:

```javascript
const fields = ["serialNumber", "basicNumber", "customerCode", "partNumber", "lineNumber"];
const results = new Map();

for (const path of fields) {
  const hits = await db.products_10M.aggregate([
    { $search: { index: "idx_identifiers_multifield", text: { query, path } } },
    { $limit: 50 },
    { $project: { _id: 1, [path]: 1, score: { $meta: "searchScore" } } }
  ]).toArray();

  for (const doc of hits) {
    const key = doc._id.toString();
    const prev = results.get(key);
    if (!prev || doc.score > prev.score) results.set(key, doc);
  }
}

const merged = [...results.values()].sort((a, b) => b.score - a.score).slice(0, 20);
```

Design tips:

- **Reuse analyzer definitions.** Define each analyzer (`kw_lc`, `kw_lc_edge`) once at the top of the index and reference by `name` — don't re-declare per field.
- **Different shapes, same index.** You can freely mix `{ type: "string" }` (default analyzer) and `{ type: "string", analyzer: "basic_path" }` (path-hierarchy) in the same `mappings.fields` block.
- **When `compound` ships**, switch fan-out merge to a server-side `should` with `minimumShouldMatch: 1` — the client code above will be deletable.

## References

- [Azure DocumentDB — full-text search](https://learn.microsoft.com/azure/documentdb/)
