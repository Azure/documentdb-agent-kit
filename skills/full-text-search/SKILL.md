---
name: documentdb-full-text-search
description: Full-text search best practices for Azure DocumentDB using the `createSearchIndexes` command and `$search` aggregation stage — BM25 keyword scoring, fuzzy search (`maxEdits`), phrase search with `slop`, custom analyzers (keyword + lowerCase + asciiFolding + edgeGram) for prefix / ID matching, `pathHierarchy` tokenizer for hierarchical IDs, multi-field search indexes, and hybrid (BM25 + vector) retrieval via Reciprocal Rank Fusion. Use when building search experiences, adding typo tolerance, matching phrases or prefixes on IDs / SKUs / part numbers, or combining lexical and semantic retrieval on the same collection.
license: MIT
---

# Full-Text Search — Azure DocumentDB (`$search` + `createSearchIndexes`)

Azure DocumentDB's full-text search is driven by search indexes built with the **`createSearchIndexes`** database command and queried through the **`$search`** aggregation stage. Scoring is **BM25**, exposed via `$meta: "searchScore"`. The community `$text` operator and `{ field: "text" }` index type are **not** the DocumentDB search path.

Key syntax points that differ from many blog posts and older docs:

- **Index command** is `createSearchIndexes` (not `createIndexes`) — each index has a `name` and a `definition.mappings.fields` block; `dynamic: false` is the safe default.
- **Custom analyzers** live inside `definition.analyzers` and are referenced per-field via `analyzer` / `searchAnalyzer`.
- **`$search` targets an index by name** via `index: "<name>"` — the engine does not auto-pick when multiple exist.
- **No `count` field** inside `$search` — use a downstream `{ $limit: N }` stage.
- **No `compound` operator yet** — query one field at a time and merge in the application (see `fts-multifield-index`).

## Rules

- [fts-create-search-index](fts-create-search-index.md) — Create a search index via `runCommand({ createSearchIndexes })`; use `definition.mappings` with `dynamic: false`.
- [fts-basic-search](fts-basic-search.md) — `$search` + `text` operator for BM25 keyword search; target `index`, project `searchScore`, cap with `$limit`.
- [fts-fuzzy-search](fts-fuzzy-search.md) — Add `fuzzy: { maxEdits: 1 }` to tolerate typos; keep `maxEdits` small.
- [fts-phrase-search](fts-phrase-search.md) — `phrase` operator with `slop` for ordered-proximity matching.
- [fts-custom-analyzers](fts-custom-analyzers.md) — Keyword tokenizer + `lowerCase` + `asciiFolding` + `edgeGram` for case-insensitive prefix matching on IDs, SKUs, part numbers. Index-time vs search-time analyzer pair.
- [fts-path-hierarchy](fts-path-hierarchy.md) — `pathHierarchy` tokenizer for hierarchical identifiers (`BN-747-ENG-2024.05`, dotted, slash paths).
- [fts-multifield-index](fts-multifield-index.md) — One search index mapping multiple fields; fan-out-and-merge in the app while `$search` `compound` is unavailable.
- [fts-hybrid-search](fts-hybrid-search.md) — Combine BM25 and vector search (RRF) on the same collection.
