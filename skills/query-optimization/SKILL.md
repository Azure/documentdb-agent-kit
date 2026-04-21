---
name: documentdb-query-optimization
description: Query and aggregation-pipeline optimization rules for Azure DocumentDB — using `explain("executionStats")` to verify index usage and avoid `COLLSCAN`. Use when reviewing a specific query, diagnosing a slow query, or validating that an index is actually being used. For full index-design workflow, see the `documentdb-query-optimizer` skill.
license: MIT
---

# Query & Aggregation Optimization — Azure DocumentDB

Best-practice rules for writing queries that can actually use indexes. For the full diagnostic workflow (explain output interpretation, ESR compound index design, covered queries, anti-patterns), see the `documentdb-query-optimizer` skill.

## Rules

- [query-explain-plan](query-explain-plan.md) — Use `explain("executionStats")` to verify index usage; watch `keysExamined` / `docsExamined` vs `nReturned`; avoid `COLLSCAN`.
