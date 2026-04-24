# cluster-tier-selection

**Category:** Cluster Design & Sharding · **Priority:** CRITICAL

## Why it matters

Azure DocumentDB is provisioned at a **cluster tier** (M10, M20, M30, M40, M60, M80, M200, …). The tier fixes vCPU, RAM, storage, and IOPS — and gates features. Notably, vector search with **DiskANN** and **HNSW** requires **M30 or higher**, while IVF is available on M10/M20 for small datasets. Undersizing the tier causes swapping (vector/index working set falls out of RAM), throttling, and tail-latency spikes; oversizing wastes money.

## Incorrect

Picking the smallest tier for an AI workload to save money:

```text
Workload: 200k product docs, 1536-dim OpenAI embeddings, DiskANN vector search
Chosen tier: M10
```

Result: DiskANN isn't available below M30, and even HNSW's memory footprint exceeds M10's RAM — queries degrade or fail.

## Correct

Size to the **binding constraint**, typically working-set memory:

| Workload profile | Starting tier |
|---|---|
| Dev / test, IVF only, <10k vectors | M10 / M20 |
| Small-to-medium app, HNSW, <50k vectors | M30 |
| Production AI, DiskANN, up to 500k+ vectors | M30 → M60+ as dataset grows |
| High-throughput OLTP, large indexes | M40 / M60+ |
| Enterprise, multi-tenant, high concurrency | M80 / M200 |

Rules of thumb:
- Keep the **hot working set** (popular indexes + recent documents + vector index) under ~60–70% of cluster RAM.
- Combine with **Product Quantization** or **Half-Precision** to fit larger vector indexes on smaller tiers (see `vector-product-quantization`, `vector-half-precision`).
- Scale **up** before you scale **out**; DocumentDB doesn't require a shard key until TB scale.

## References

- [Scale a cluster](https://learn.microsoft.com/azure/documentdb/how-to-scale-cluster)
- [Vector search](https://learn.microsoft.com/azure/documentdb/vector-search)
