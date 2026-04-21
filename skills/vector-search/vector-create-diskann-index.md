# vector-create-diskann-index

**Category:** Vector Search · **Priority:** HIGH

## Why it matters

DiskANN is the recommended vector index in Azure DocumentDB for production-scale workloads. Its `maxDegree`, `lBuild`, and the query-time `lSearch` parameters trade off build time, memory, recall, and query latency. The `dimensions` and `similarity` values **must match** the embeddings you insert — mismatches produce wrong results silently.

Parameter guide:

| Parameter | Range | Default | Notes |
|---|---|---|---|
| `dimensions` | 1–16,000 (with PQ) | — | Must match embedding model output exactly |
| `similarity` | `COS`, `L2`, `IP` | — | Use `COS` for normalized text embeddings |
| `maxDegree` | 20–2048 | 32 | Higher → better recall, more memory / slower build |
| `lBuild` | 10–500 | 50 | Higher → better index quality, slower build |
| `lSearch` (query-time) | 10–1000 | 40 | Higher → better recall, slower queries; must be ≥ `k` |

## Incorrect

```javascript
// Wrong dimensions vs. the embedding model -> silently-incorrect results
db.products.createIndex(
  { embedding: "cosmosSearch" },
  { cosmosSearchOptions: { kind: "vector-diskann", dimensions: 768, similarity: "L2" } }
);
// ...but the app uses 1536-dim OpenAI text-embedding-3-small with cosine similarity.
```

## Correct

```javascript
db.products.createIndex(
  { embedding: "cosmosSearch" },
  {
    name: "products_embedding_diskann",
    cosmosSearchOptions: {
      kind: "vector-diskann",
      dimensions: 1536,       // matches text-embedding-3-small
      similarity: "COS",      // matches the query-time similarity
      maxDegree: 32,
      lBuild: 50
    }
  }
);
```

If you change embedding models, **rebuild the index** — mixing dimensions or similarities corrupts results.

## References

- [Vector search — DiskANN index creation](https://learn.microsoft.com/azure/documentdb/vector-search)
