---
name: documentdb-data-modeling
description: Data modeling patterns for Azure DocumentDB — embed vs reference, 16 MB document limit, denormalization for read-heavy workloads, schema versioning. Use when designing new schemas, reviewing existing data models, migrating from SQL, deciding between embedding and referencing, modeling one-to-one / one-to-many / many-to-many relationships, or troubleshooting document-size and query-performance problems that stem from the data model.
license: MIT
---

# Data Modeling — Azure DocumentDB

Guiding principle: **"Data that is accessed together should be stored together."**

Each rule follows the same shape — why it matters → incorrect example → correct example → references.

## Rules

- [model-embed-vs-reference](model-embed-vs-reference.md) — Embed data accessed together; reference unbounded N-sides.
- [model-16mb-limit](model-16mb-limit.md) — Stay well under the 16 MB BSON document limit; plan for steady-state growth.
- [model-denormalize-reads](model-denormalize-reads.md) — Denormalize for read-heavy workloads; pre-compute aggregates to avoid `$lookup`.
- [model-schema-versioning](model-schema-versioning.md) — Add a `schemaVersion` field and migrate documents lazily.

## Decision framework

| Relationship | Cardinality | Access pattern | Recommendation |
|---|---|---|---|
| One-to-One | 1:1 | Always together | Embed |
| One-to-Few | 1:N (N < ~100) | Usually together | Embed array |
| One-to-Many | 1:N (N > ~100) | Often separate | Reference |
| Many-to-Many | M:N | Varies | Two-way reference or junction collection |

See each rule file for the full reasoning and code examples.
