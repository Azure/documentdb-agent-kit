# Verify index usage with `explain()` — the first check

> Reference doc for the `documentdb-query-optimizer` skill (merged from the former
> `documentdb-query-optimization` rule). Load this to verify — **before** changing
> anything — whether a query actually uses an index or is doing a `COLLSCAN`.

## Why it matters

Guessing query performance is unreliable. `explain("executionStats")` is the
ground truth: it reveals whether a query used an index (`IXSCAN`), did a full
collection scan (`COLLSCAN`), was targeted to a single shard, or was
scatter-gather. Run it as the **first** step of any optimization — and as part of
PR review for any new hot-path query — before recommending an index.

## Read the plan first — then beware the confounders

`explain()` is where you start, but three signals in it routinely mislead. Check
the plan **first**, and do not trust these at face value:

1. **The top-line numbers lie.** Azure DocumentDB's planner is PostgreSQL-backed,
   so the top-level `executionTimeMillis` and `totalDocsExamined` are *post-sort /
   post-merge* and can look healthy even during a full scan. **Drill into the
   nested `inputStage` down to the `COLLSCAN`/`IXSCAN`** and read *its*
   `totalDocsExamined` / `totalKeysExamined`. A query that returns in a few
   milliseconds can still be scanning the whole collection.
2. **An index existing ≠ the index being used.** Check `winningPlan.indexName`.
   The planner may ignore an index that isn't selective for this query shape, so
   "there's already an index" does not mean the query is fine.
3. **Scatter-gather masquerades as a slow query.** On a sharded collection,
   `shards[]` hitting *every* shard is the real cost — not a missing index. Fix it
   by including the shard key in the filter, not by adding another index.

## Incorrect

```javascript
// Ship it, hope it's fast in prod.
const results = await db.orders.find(filter).sort(sort).toArray();
```

## Correct

```javascript
const plan = await db.orders.find(filter).sort(sort).explain("executionStats");
// Review, in order:
//  1. the SCAN stage (drill into inputStage): IXSCAN (good) vs COLLSCAN (bad)
//  2. scan-stage totalDocsExamined / totalKeysExamined vs nReturned (ratio ~1 is ideal)
//  3. a blocking SORT stage (sort not served by the index)
//  4. shards[]: all shards hit => scatter-gather, fix with the shard key in the filter
```

Automate it in CI with a small harness that asserts
`scan-stage totalDocsExamined / nReturned < threshold` for critical queries, so a
regression to `COLLSCAN` fails the build.

## References

- MongoDB [`explain()`](https://www.mongodb.com/docs/manual/reference/method/cursor.explain/) docs
- Companion: [`core-indexing-principles.md`](core-indexing-principles.md) · the `documentdb-query-performance-tuning` skill's `references/documentdb-explain-output.md` (full DocumentDB explain field glossary)
