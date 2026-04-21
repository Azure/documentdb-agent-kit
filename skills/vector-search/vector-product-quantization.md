# vector-product-quantization

**Category:** Vector Search · **Priority:** HIGH

## Why it matters

High-dimensional embeddings (1536, 3072, up to 16,000 dims) consume a lot of memory, which caps how large a vector index you can keep resident on a given cluster tier. **Product Quantization (PQ)** compresses vectors by splitting them into sub-vectors and representing each with a small codebook index, typically cutting memory **4×–32×** with a small, tunable recall loss. Azure DocumentDB supports PQ for DiskANN indexes.

Use PQ when:
- Your vector index exceeds ~60–70% of cluster RAM, or
- You need to keep a larger collection on the same tier, or
- You want to reduce cost by staying on a smaller M-tier for the same workload.

## Incorrect

Upgrading the cluster tier purely because the vector index no longer fits in RAM:

```text
Symptom: DiskANN index for 1M × 3072-dim vectors doesn't fit on M40.
Reaction: Scale to M80 — expensive and larger than needed for CPU/IOPS.
```

## Correct

Enable PQ on the DiskANN index to shrink memory usage first; only scale up if CPU/IOPS (not memory) becomes the bottleneck.

```javascript
// Consult the current Azure DocumentDB docs for the exact PQ option
// names and ranges — verify before production use.
db.products.createIndex(
  { embedding: "cosmosSearch" },
  {
    name: "products_embedding_diskann_pq",
    cosmosSearchOptions: {
      kind: "vector-diskann",
      dimensions: 3072,
      similarity: "COS",
      maxDegree: 32,
      lBuild: 50,
      // Product Quantization options — see docs for exact field names
      productQuantization: {
        enabled: true,
        pqDims: 96,     // number of sub-vectors (must divide dimensions)
        pqBits: 8       // bits per sub-vector code
      }
    }
  }
);
```

Validate recall after enabling PQ with a held-out query set; raise `lSearch` at query time to recover any recall lost to quantization.

## References

- [Product Quantization for DiskANN in Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/product-quantization)
