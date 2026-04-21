# vector-choose-index-type

**Category:** Vector Search · **Priority:** HIGH

## Why it matters

Azure DocumentDB supports three `cosmosSearch` vector index types and each has a clear sweet spot. Picking the wrong one costs recall, latency, or memory.

| Index | Vector count | Cluster tier | Pros | Cons |
|---|---|---|---|---|
| `vector-ivf` (IVF / IVFFlat) | under 10,000 | M10 / M20 | Fast to build, low memory | Lower recall/latency tradeoff |
| `vector-hnsw` (HNSW) | up to 50,000 | M30+ | Good recall, can be built on empty collections | Slower build, more memory |
| `vector-diskann` (DiskANN) — **recommended** | 500,000+ and beyond | M30+ | High recall, high throughput, low latency, scales | Requires M30+ |

## Incorrect

Using IVF for a production 200k-vector AI workload — recall and latency will disappoint:

```javascript
db.products.createIndex(
  { embedding: "cosmosSearch" },
  { cosmosSearchOptions: { kind: "vector-ivf", numLists: 100, similarity: "COS", dimensions: 1536 } }
);
```

## Correct

```javascript
// Production AI workload on M30+
db.products.createIndex(
  { embedding: "cosmosSearch" },
  {
    name: "products_embedding_diskann",
    cosmosSearchOptions: {
      kind: "vector-diskann",
      dimensions: 1536,
      similarity: "COS",
      maxDegree: 32,
      lBuild: 50
    }
  }
);
```

If memory is tight, combine DiskANN with **Product Quantization** or **Half-Precision** indexing (see related rules).

## References

- [Vector search — index type guidance](https://learn.microsoft.com/azure/documentdb/vector-search)
