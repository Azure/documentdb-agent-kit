---
name: documentdb-vector-search
description: Vector search best practices for Azure DocumentDB using `cosmosSearch` — choosing between DiskANN / HNSW / IVF, creating indexes, tuning `lBuild` / `lSearch` / `maxDegree`, Product Quantization (up to 16,000 dims), half-precision (fp16) indexing, and normalizing embeddings for cosine similarity. Use when building RAG / semantic-search applications, creating a vector index, tuning recall/latency, or reducing vector-index memory footprint.
license: MIT
---

# Vector Search — Azure DocumentDB (`cosmosSearch`)

Azure DocumentDB's native vector index type is `cosmosSearch`. Pick the sub-type by scale:

| Index sub-type | Scale sweet spot | Tier |
|---|---|---|
| `vector-diskann` (recommended) | Up to 500k+ vectors | M30+ |
| `vector-hnsw` | Up to ~50k vectors | M30+ |
| `vector-ivf` | Under ~10k vectors | M10+ |

Similarity options: `COS` (cosine), `L2` (Euclidean), `IP` (inner product).

## Rules

- [vector-choose-index-type](vector-choose-index-type.md) — Prefer DiskANN for production; use HNSW up to 50k, IVF under 10k.
- [vector-create-diskann-index](vector-create-diskann-index.md) — Create a `vector-diskann` index with correct `dimensions`, `similarity`, `maxDegree`, and `lBuild`.
- [vector-knn-query](vector-knn-query.md) — Query with `$search` + `cosmosSearch`; tune `lSearch` and `k`; combine with pre-filters.
- [vector-product-quantization](vector-product-quantization.md) — Shrink high-dimensional vectors (up to 16,000 dims) while preserving recall.
- [vector-half-precision](vector-half-precision.md) — Halve vector memory with fp16 indexing and minimal recall loss.
- [vector-normalize-embeddings](vector-normalize-embeddings.md) — Normalize embeddings when using cosine similarity; store model + dimensions alongside vectors.
