# fts-hybrid-search

**Category:** Full-Text Search · **Priority:** MEDIUM

## Why it matters

Keyword search (BM25 via `textSearch`) and vector search (`cosmosSearch` DiskANN) each fail in predictable ways:
- Keyword search misses paraphrases and synonyms.
- Vector search misses exact identifiers, part numbers, and rare terms.

**Hybrid search** runs both and fuses the result lists, typically giving higher recall *and* precision than either alone. Azure DocumentDB supports both indexes on the same collection, so you can execute both queries in one round trip and combine them in the application or via Reciprocal Rank Fusion (RRF).

## Incorrect

Shipping keyword-only search when users paste semantic queries (`"waterproof hiking jacket for cold weather"`) — misses products that don't share those exact tokens.

Or shipping vector-only search for a catalog where users type SKUs (`"SKU-4821-A"`) — embeddings don't preserve exact identifiers well.

## Correct

1. Index both on the collection:

```javascript
// BM25 on the searchable text
db.runCommand({
  createIndexes: "products",
  indexes: [{ key: { description: "textSearch" }, name: "desc_fts" }]
});

// Vector on the embedding
db.products.createIndex(
  { embedding: "cosmosSearch" },
  {
    name: "desc_diskann",
    cosmosSearchOptions: {
      kind: "vector-diskann",
      dimensions: 1536,
      similarity: "COS"
    }
  }
);
```

2. Run both queries and fuse with RRF (simple, effective):

```javascript
const kwHits = await db.products.aggregate([
  { $search: { text: { query: userQuery, path: "description" }, count: 50 } },
  { $project: { _id: 1, kw: { $meta: "searchScore" } } }
]).toArray();

const qv = await embed(userQuery);
const vecHits = await db.products.aggregate([
  { $search: { cosmosSearch: { path: "embedding", query: qv, k: 50 } } },
  { $project: { _id: 1, vec: { $meta: "searchScore" } } }
]).toArray();

// Reciprocal Rank Fusion (k=60 is a common default)
function rrf(lists, k = 60) {
  const scores = new Map();
  for (const list of lists) {
    list.forEach((doc, rank) => {
      const cur = scores.get(doc._id.toString()) ?? 0;
      scores.set(doc._id.toString(), cur + 1 / (k + rank + 1));
    });
  }
  return [...scores.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([id, score]) => ({ _id: id, score }));
}

const fused = rrf([kwHits, vecHits]);
```

Tips:
- Keep individual `count` / `k` modest (20–100) — RRF doesn't need deep lists to improve quality.
- If one signal is clearly more reliable for a workload, weight it: `score += w / (k + rank)`.
- Cache embeddings for popular queries to reduce per-request latency.

## References

- [Vector search in Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/vector-search)
- [Azure DocumentDB overview](https://learn.microsoft.com/azure/documentdb/overview)
