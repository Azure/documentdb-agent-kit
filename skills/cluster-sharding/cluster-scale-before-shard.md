# cluster-scale-before-shard

**Category:** Cluster Design & Sharding · **Priority:** CRITICAL

## Why it matters

Azure DocumentDB **does not require a shard key** until the database surpasses terabyte scale. Many MongoDB best-practice guides assume Atlas-style sharding on day one; applying that advice to DocumentDB adds complexity and constrains queries unnecessarily.

Scale order for DocumentDB:

1. **Vertical (cluster tier)** — pick the right M-tier for working-set memory and vCPU.
2. **Indexing and query tuning** — the usual compound indexes, ESR ordering, projection.
3. **Vector footprint reduction** — Product Quantization, Half-Precision for AI workloads.
4. **Cross-region read replica** — offload reads to another region if needed.
5. **Explicit sharding** — only when the database grows to terabytes or a single node's storage/IOPS saturates.

## Incorrect

Premature sharding of a 20 GB collection:

```javascript
// Day-1 sharding on a medium collection — unneeded complexity
db.orders.shardCollection({ customerId: "hashed" });
// Now every query must include customerId to be targeted;
// cross-customer analytics becomes scatter-gather.
```

## Correct

```text
- Start on an appropriate cluster tier (see cluster-tier-selection).
- Monitor CPU, memory, IOPS, and storage headroom.
- Add compound indexes for hot queries; verify with explain().
- Only introduce explicit sharding when:
    * total storage > ~1 TB, OR
    * a single node's IOPS is saturated and vertical scale options are exhausted.
- When you do shard, follow cluster-shard-key-query-aligned.
```

## References

- [Azure DocumentDB overview — flexible and scalable data management](https://learn.microsoft.com/azure/documentdb/overview#flexible-and-scalable-data-management)
- [Scale a cluster](https://learn.microsoft.com/azure/documentdb/how-to-scale-cluster)
