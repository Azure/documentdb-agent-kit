# vector-half-precision

**Category:** Vector Search · **Priority:** HIGH

## Why it matters

Embedding vectors are typically stored as 32-bit floats (fp32). **Half-precision (fp16) indexing** stores index coordinates as 16-bit floats, cutting vector-index memory roughly **2×** with minimal recall impact for most text and image embedding models. On Azure DocumentDB this is a lighter-weight alternative to Product Quantization — simpler to turn on, less recall tradeoff, but smaller memory savings.

Use half-precision when:
- PQ's compression is more than you need, and you want a simpler switch.
- You want to roughly double the vector count that fits on the same M-tier.
- Your embeddings come from models that tolerate fp16 (most modern ones do).

## Incorrect

Falling back to a larger cluster tier because the fp32 DiskANN index is ~1.8× too big for the current tier's RAM budget:

```text
Current: M40, 1M × 1536-dim fp32 vectors ≈ 6 GB index, borderline.
Reaction: scale to M60 for headroom.
```

## Correct

Enable half-precision first; reassess headroom before scaling up.

```javascript
// Exact field name(s) should be verified against the current docs.
db.products.createIndex(
  { embedding: "cosmosSearch" },
  {
    name: "products_embedding_diskann_hp",
    cosmosSearchOptions: {
      kind: "vector-diskann",
      dimensions: 1536,
      similarity: "COS",
      maxDegree: 32,
      lBuild: 50,
      halfPrecision: true   // fp16 index storage
    }
  }
);
```

Run an A/B recall check against the prior fp32 index with a representative query set; for most production text embeddings the delta is well under 1%.

## References

- [Half-Precision Vector Indexing](https://learn.microsoft.com/azure/documentdb/half-precision)
