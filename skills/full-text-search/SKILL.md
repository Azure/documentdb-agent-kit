---
name: documentdb-full-text-search
description: Full-text search best practices for Azure DocumentDB using the `textSearch` index and `$search` aggregation stage — BM25 keyword scoring, fuzzy search (`maxEdits`), phrase search with `slop`, and hybrid (BM25 + vector) retrieval via Reciprocal Rank Fusion. Use when building search experiences, adding typo tolerance, matching phrases, or combining lexical and semantic retrieval on the same collection.
license: MIT
---

# Full-Text Search — Azure DocumentDB (`textSearch`)

Azure DocumentDB's full-text search uses a dedicated **`textSearch`** index type queried through the **`$search`** aggregation stage — **not** the community `$text` operator. Scoring is BM25; the score is exposed via `$meta: "searchScore"`.

## Rules

- [fts-create-textsearch-index](fts-create-textsearch-index.md) — Create a `textSearch` index via `runCommand({ createIndexes })` before running `$search`.
- [fts-basic-search](fts-basic-search.md) — Use `$search` + `text` operator for BM25 keyword search; project `searchScore`.
- [fts-fuzzy-search](fts-fuzzy-search.md) — Add `fuzzy: { maxEdits }` to tolerate typos; keep `maxEdits` small (1–2).
- [fts-phrase-search](fts-phrase-search.md) — Use the `phrase` operator with `slop` for ordered-proximity matching.
- [fts-hybrid-search](fts-hybrid-search.md) — Combine BM25 and vector search (RRF) on the same collection for best recall + precision.
