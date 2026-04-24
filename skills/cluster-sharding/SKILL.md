---
name: documentdb-cluster-sharding
description: Cluster sizing and sharding guidance for Azure DocumentDB — choosing M-tier (M10–M200+), when to scale vertically vs horizontally, and how to pick a shard key once the database surpasses terabyte scale. Use when sizing a new cluster, diagnosing capacity issues, deciding whether to shard, or designing a shard key.
license: MIT
---

# Cluster Design & Sharding — Azure DocumentDB

In Azure DocumentDB, a shard key is **not required** until the database surpasses terabytes. Most scaling decisions are about picking the right M-tier first.

## Rules

- [cluster-tier-selection](cluster-tier-selection.md) — Pick an M-tier (M10–M200+) based on working-set memory, vCPU, and vector-index size.
- [cluster-scale-before-shard](cluster-scale-before-shard.md) — Scale vertically first; DocumentDB doesn't require a shard key until TB scale.
- [cluster-shard-key-query-aligned](cluster-shard-key-query-aligned.md) — When you do shard at TB scale, pick a high-cardinality, query-aligned, immutable shard key.
