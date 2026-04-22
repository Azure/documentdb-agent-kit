# fts-custom-analyzers

**Category:** Full-Text Search · **Priority:** HIGH

## Why it matters

The default standard analyzer tokenises on whitespace + punctuation and case-folds — fine for prose, **useless for identifiers** like `AB2` or `ABX098` where the user expects prefix / partial matching, or for mixed-case content where `"CRM"` must match `"Crm"`.

Custom analyzers in Azure DocumentDB are defined inside the search-index `definition` and consist of:

- A **tokenizer** (`keyword`, `standard`, `pathHierarchy`, …) — how the raw value is chopped.
- A chain of **token filters** (`lowerCase`, `asciiFolding`, `edgeGram`, …) — transforms applied to each token.

Assign an **`analyzer`** to a field to control index-time tokenisation, and optionally a **`searchAnalyzer`** to control query-time tokenisation. Using different analyzers at index and query time is how prefix matching works: index the value as every prefix (`edgeGram`), search the query as one keyword token.

## Incorrect

Relying on the default analyzer for ID-style fields — prefix searches silently fail:

```javascript
// ❌ partNumber indexed with default analyzer — "AB2" finds nothing
db.runCommand({
  createSearchIndexes: "products_10M",
  indexes: [{
    name: "idx_partNumber_default",
    definition: { mappings: { dynamic: false, fields: { partNumber: { type: "string" } } } }
  }]
});

db.products_10M.aggregate([
  { $search: { index: "idx_partNumber_default",
               text: { query: "AB2", path: "partNumber" } } },
  { $limit: 20 }
]);
// Returns only documents where partNumber equals exactly "AB2" (after tokenisation).
```

Using `edgeGram` on both index and search sides — explodes the query into prefixes and matches way too much:

```javascript
// ❌ Same analyzer on both sides produces cartesian-like matches
partNumber: { type: "string", analyzer: "kw_lc_edge", searchAnalyzer: "kw_lc_edge" }
```

## Correct

**Prefix matching on an ID field** — `edgeGram` at index time, plain `keyword` at search time:

```javascript
db.runCommand({
  createSearchIndexes: "products_10M",
  indexes: [
    {
      name: "idx_partNumber_prefix",
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
            partNumber: {
              type: "string",
              analyzer:       "kw_lc_edge",   // index-time: produce every prefix
              searchAnalyzer: "kw_lc"         // query-time: treat the query as one token
            }
          }
        }
      }
    }
  ]
});

// Prefix match — "AB2" finds "ABX098", "AB29000", …
db.products_10M.aggregate([
  { $search: {
      index: "idx_partNumber_prefix",
      text: { query: "AB2", path: "partNumber" }
  }},
  { $limit: 20 },
  { $project: { _id: 0, partNumber: 1, score: { $meta: "searchScore" } } }
]);

// Exact match still works — full value matches its own longest edge-gram
db.products_10M.aggregate([
  { $search: {
      index: "idx_partNumber_prefix",
      text: { query: "ABX098", path: "partNumber" }
  }},
  { $limit: 20 }
]);
```

Design tips:

- **Token filter order matters.** `lowerCase` → `asciiFolding` → `edgeGram` is the safe order; doing `edgeGram` before case-folding produces many redundant prefixes.
- **Cap `maxGram`.** Leaving `maxGram` at 255 for very long strings bloats the index; cap it to the realistic ID length.
- **`keyword` tokenizer** treats the whole value as one token — essential for IDs, SKUs, codes. `standard` would split `"ABX098"` on digits.
- **One analyzer pair per "shape" of field.** Reuse the same `(kw_lc_edge, kw_lc)` pair for every prefix-matching ID field rather than defining one pair per field.
- **Compare to `$regex` prefix**: `$regex: "^AB2"` forces a `COLLSCAN` and does no ranking. An `edgeGram`-indexed `$search` is O(log n), ranked, and tolerates mixed case.

## References

- [Azure DocumentDB — full-text search](https://learn.microsoft.com/azure/documentdb/)
