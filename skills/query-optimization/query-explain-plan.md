# query-explain-plan

**Category:** Query & Aggregation Optimization · **Priority:** HIGH

## Why it matters

Guessing query performance is unreliable. `explain("executionStats")` reveals whether a query used an index (`IXSCAN`), did a collection scan (`COLLSCAN`), was targeted to a shard, or was scatter-gather. Use it as part of PR review for any new hot-path query.

## Incorrect

```javascript
// Ship it, hope it's fast in prod.
const results = await db.orders.find(filter).sort(sort).toArray();
```

## Correct

```javascript
const plan = await db.orders.find(filter).sort(sort).explain("executionStats");
// Review:
//  - winningPlan.stage: IXSCAN (good) vs COLLSCAN (bad)
//  - executionStats.totalDocsExamined vs nReturned (ratio close to 1 is ideal)
//  - shards[]: all shards hit => scatter-gather, fix with shard key in filter
```

Automate in CI with a small harness that asserts `totalDocsExamined / nReturned < threshold` for critical queries.

## References

- MongoDB [`explain()`](https://www.mongodb.com/docs/manual/reference/method/cursor.explain/) docs
