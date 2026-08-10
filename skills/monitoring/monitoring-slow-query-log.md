# monitoring-slow-query-log

**Category:** Monitoring & Diagnostics · **Priority:** MEDIUM

## Why it matters

Most production performance issues on Azure DocumentDB come from a handful of unindexed or misaligned queries that start as `COLLSCAN` and grow linearly with the collection. Without diagnostic logs you can't find them; with them, you can systematically hunt down the worst offenders.

Set up:
1. Enable **Diagnostic Settings** on the cluster and route logs to a **Log Analytics workspace** (or Event Hub / Storage).
2. Enable slow-query / operation logs in the settings.
3. Build a Kusto dashboard ranked by total duration and docs examined.
4. Review weekly; feed the top 10 queries back into index design.

## Incorrect

Relying on ad-hoc `db.currentOp()` checks during incidents with no historical log.

## Correct

Kusto example against the `VCoreMongoRequests` diagnostic log table — rank the slowest operations, then run `explain()` on each candidate:

```kusto
// Top 20 slowest operations (> 1s) — copy PiiCommandText and run explain() on it
VCoreMongoRequests
| where DurationMs > 1000
| project TimeGenerated, DatabaseName, CollectionName,
          OperationName, DurationMs, PiiCommandText
| order by DurationMs desc
| take 20
```

Key columns: `DurationMs` (execution time), `OperationName` (`find` / `aggregate` / `update` / …), `CollectionName`, and `PiiCommandText` (the actual command that ran). Copy `PiiCommandText` for a candidate and run `explain("executionStats")` on it — see the `documentdb-query-performance-tuning` skill (and its [`references/documentdb-explain-output.md`](../query-performance-tuning/references/documentdb-explain-output.md)) for how to read Azure DocumentDB's explain output.

To aggregate by query shape over a window instead:

```kusto
VCoreMongoRequests
| where TimeGenerated > ago(24h)
| summarize
    count(),
    avg_duration_ms = avg(DurationMs),
    total_duration_ms = sum(DurationMs)
  by DatabaseName, CollectionName, OperationName
| order by total_duration_ms desc
| take 20
```

Action items from this dashboard typically include: adding a compound index, adjusting ESR ordering, fixing an unbounded query, or switching a regex to a prefix-anchored form.

## References

- [Query Performance Tuning Guide](https://devblogs.microsoft.com/documentdb/query-performance-tuning-guide/) (devblog)
- [How to monitor diagnostics logs](https://learn.microsoft.com/en-us/azure/documentdb/how-to-monitor-diagnostics-logs)
- [Azure Monitor for Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/)
