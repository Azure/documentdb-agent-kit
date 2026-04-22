# fts-create-search-index

**Category:** Full-Text Search · **Priority:** HIGH

## Why it matters

Azure DocumentDB full-text search is driven by a **search index** created with the `createSearchIndexes` database command — **not** `createIndexes` with a `"text"` or `"textSearch"` key type. The search index is separate from regular MQL indexes (it does **not** show up the same way in `getIndexes()`) and defines:

1. **Mappings** — which fields are searchable, their types, and optional per-field analyzers.
2. **Analyzers** (optional) — custom tokenizers and token filters.

Without the search index, a `$search` aggregation stage on that field/collection returns nothing useful.

## Incorrect

Using the community MongoDB text-index shape, which is not the Azure DocumentDB search path:

```javascript
// ❌ Not the Azure DocumentDB search path
db.products.createIndex({ title: "text" });

// ❌ Also wrong — the DocumentDB search engine does not consume this form
db.runCommand({
  createIndexes: "products",
  indexes: [{ key: { title: "textSearch" }, name: "title_fts" }]
});
```

## Correct

Use `createSearchIndexes` with a `definition.mappings` block. Set `dynamic: false` and enumerate the fields explicitly so index growth is predictable:

```javascript
db.runCommand({
  createSearchIndexes: "products_10M",
  indexes: [
    {
      name: "idx_title_standard",
      definition: {
        mappings: {
          dynamic: false,
          fields: {
            title: { type: "string" }
          }
        }
      }
    }
  ]
});

// Verify
db.products_10M.getIndexes();
```

Guidelines:

- **Name the index descriptively** (`idx_<field>_<intent>`). You reference it in `$search` via `index: "<name>"`, so names matter.
- **`dynamic: false` + explicit `fields`** — prevents every string field from being indexed. Don't enable `dynamic: true` on large collections.
- **One field → one mapping entry.** For multiple searchable fields, use a single index with multiple entries (see `fts-multifield-index`), not multiple indexes per field.
- **Add custom analyzers only when needed** — prefix matching, hierarchical IDs, language-specific folding. See `fts-custom-analyzers` and `fts-path-hierarchy`.
- **Build before bulk load** if possible, or build on a populated collection and allow time to catch up.

## References

- [Azure DocumentDB overview](https://learn.microsoft.com/azure/documentdb/overview)
- [MQL compatibility](https://learn.microsoft.com/azure/documentdb/compatibility-query-language)
