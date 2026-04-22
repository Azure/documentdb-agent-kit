# fts-path-hierarchy

**Category:** Full-Text Search · **Priority:** MEDIUM

## Why it matters

Hierarchical identifiers — `BN-747-ENG-2024.05`, `/regions/eu/ops`, `com.example.service` — need a tokenizer that produces each progressively longer prefix as a searchable token, so that a query on any ancestor matches the whole value.

The **`pathHierarchy` tokenizer** does this: with `delimiter: "-"`, the value `BN-747-ENG-2024.05` indexes as:

- `BN`
- `BN-747`
- `BN-747-ENG`
- `BN-747-ENG-2024.05`

So a search for `"BN"`, `"bn-747"`, or `"BN-747-ENG"` all find the same document. Plain tokenization would split on `-` and match any of those fragments out of order — bad precision. `edgeGram` would match any character prefix (`B`, `BN`, `BN-`, `BN-7`, …) — too broad.

## Incorrect

Using `edgeGram` for hierarchical IDs — matches character prefixes that aren't real ancestors:

```javascript
// ❌ "BN-7" would match; so would "BN-74", which isn't a legit path boundary
definition: {
  analyzers: [{
    name: "edge",
    tokenizer: { type: "keyword" },
    tokenFilters: [{ type: "edgeGram", minGram: 1, maxGram: 255 }]
  }],
  mappings: { dynamic: false, fields: { basicNumber: { type: "string", analyzer: "edge" } } }
}
```

Using the default analyzer — splits on `-`, matches any segment in any order:

```javascript
// ❌ "ENG" alone would match any doc with ENG anywhere
mappings: { dynamic: false, fields: { basicNumber: { type: "string" } } }
```

## Correct

```javascript
db.runCommand({
  createSearchIndexes: "products_10M",
  indexes: [
    {
      name: "idx_basicNumber_path_prefix",
      definition: {
        analyzers: [
          {
            name: "basic_path",
            tokenizer: { type: "pathHierarchy", delimiter: "-" },
            tokenFilters: [
              { type: "lowerCase" },
              { type: "asciiFolding" }
            ]
          }
        ],
        mappings: {
          dynamic: false,
          fields: {
            basicNumber: { type: "string", analyzer: "basic_path" }
          }
        }
      }
    }
  ]
});

// All three find BN-789-ENG-2024.05
db.products_10M.aggregate([
  { $search: {
      index: "idx_basicNumber_path_prefix",
      text: { query: "bn-789", path: "basicNumber" }
  }},
  { $limit: 20 },
  { $project: { _id: 0, basicNumber: 1, score: { $meta: "searchScore" } } }
]);
```

Design tips:

- **Pick the right delimiter.** Dotted hierarchies (`com.example.foo`) use `delimiter: "."`; slash paths (`/a/b/c`) use `/`. Only one delimiter per analyzer.
- **Case-fold if users type mixed case.** The `lowerCase` + `asciiFolding` filters mean `bn-789`, `BN-789`, and `bñ-789` all match.
- **`pathHierarchy` doesn't do mid-hierarchy match.** A query on `"747"` alone will **not** match `BN-747-ENG` — only ancestors match. If you also need mid-path tokens, index the same field with a second analyzer (e.g. keyword-tokenised) under a different index.
- **Use `.explain("executionStats")`** to confirm the `$search` stage is hitting the index:
  ```javascript
  db.products_10M.aggregate([...]).explain("executionStats");
  ```

## References

- [Azure DocumentDB — full-text search](https://learn.microsoft.com/azure/documentdb/)
