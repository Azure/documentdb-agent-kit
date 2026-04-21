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

Kusto example (exact table/column names depend on the current diagnostic schema — verify in your workspace):

```kusto
// Top 20 slow operations in the last 24h
DocumentDBSlowQueries_CL   // or the current table name
| where TimeGenerated > ago(24h)
| summarize
    count(),
    avg_duration_ms = avg(DurationMs),
    total_duration_ms = sum(DurationMs),
    avg_docs_examined = avg(DocsExamined)
  by Namespace, QueryShape
| order by total_duration_ms desc
| take 20
```

Action items from this dashboard typically include: adding a compound index, adjusting ESR ordering, fixing an unbounded query, or switching a regex to a prefix-anchored form.

## References

- [Azure Monitor for Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/)
- [MQL compatibility](https://learn.microsoft.com/azure/documentdb/compatibility-query-language)
