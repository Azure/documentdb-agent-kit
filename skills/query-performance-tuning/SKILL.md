---
name: documentdb-query-performance-tuning
description: >-
  End-to-end query performance tuning methodology for Azure DocumentDB. Use when
  the user asks how to tune query performance, read or interpret
  `explain("executionStats")` output, understand the ESR (Equality-Sort-Range)
  rule, eliminate a `COLLSCAN` or an in-memory sort, design a compound index for
  a query shape, confirm a sort is index-backed, use covered queries, or find
  slow queries in production via Diagnostic Logs / Log Analytics
  (`VCoreMongoRequests`). Covers DocumentDB's PostgreSQL-backed explain format
  (`PARALLEL_SORT_MERGE`, cost estimates, `runtimeFilterSet`, `indexUsage`,
  `indexCosts`). For interactive MCP-driven optimization of one specific query,
  use `documentdb-query-optimizer` instead.
license: MIT
---

# Query Performance Tuning — Azure DocumentDB

Writing a query that *works* is easy; writing one that *scales* is not. As a
collection grows to millions of documents, a query that was instant in
development starts taking seconds — almost always because the database is doing
far more work than it needs to. A single well-designed index can turn an
**81.3 ms** query into a **0.053 ms** one with **no application code change**.

This skill is the repeatable mental model:

> **find the slow query → read `explain()` → apply ESR → confirm the sort is
> index-backed → (optionally) cover the query.**

Source: [Query Performance Tuning Guide](https://devblogs.microsoft.com/documentdb/query-performance-tuning-guide/) (Azure DocumentDB devblog).

## When to use this skill

- "How do I tune / speed up this query?" (methodology, not a live MCP session)
- "How do I read / interpret `explain()` output on DocumentDB?"
- "What is the ESR rule / how do I order a compound index?"
- "Why is my query doing a `COLLSCAN` / an in-memory `SORT`?"
- "What is a covered query and when is it worth it?"
- "How do I find the slowest queries in production?"

For hands-on optimization of one specific query against a live cluster (running
`explain_operation`, proposing and creating an index via MCP), use the
**`documentdb-query-optimizer`** skill. This skill is the underlying theory both
share.

## Step 0 — Find the slow queries first

Before running `explain()`, know *which* query to investigate. On Azure
DocumentDB this uses **Diagnostic Logs** routed to an **Azure Log Analytics**
workspace (see the `documentdb-monitoring` skill to enable diagnostic settings).
Then rank the slowest operations with KQL:

```kusto
VCoreMongoRequests
| where DurationMs > 1000
| project TimeGenerated, DatabaseName, CollectionName,
          OperationName, DurationMs, PiiCommandText
| order by DurationMs desc
| take 20
```

`DurationMs` = execution time; `OperationName` = `find` / `aggregate` / …;
`PiiCommandText` = the actual command. Copy a candidate and run
`explain("executionStats")` on it.

## The problem query

```javascript
db.orders.find({
  status: "shipped",
  customerId: "C-4821",
  createdAt: { $gte: ISODate("2024-01-01") }
}).sort({ createdAt: -1 })
```

Innocent-looking, but on a 1,000,000-document collection it becomes the worst
offender under load. The five steps below fix it.

## Step 1 — Run `explain()` and read the scan stage

```javascript
db.orders.find({ /* … */ }).sort({ createdAt: -1 }).explain("executionStats")
```

The damning part is the innermost stage:

```json
"stage": "COLLSCAN",
"totalDocsExamined": 333333,
"totalDocsRemovedByRuntimeFilter": 333327,
"nReturned": 6
```

**333,333 documents scanned to return 18** (across parallel workers) — a ~99.99%
waste. `COLLSCAN` = no index used.

> **Read the scan stage, not the top stage.** Azure DocumentDB's planner is
> PostgreSQL-backed, so the top `PARALLEL_SORT_MERGE` stage reports *post-merge*
> counts that can look tiny (`totalDocsExamined: 18`) even during a full scan.
> Always drill into `inputStage` down to the `COLLSCAN`/`IXSCAN`. For the full
> DocumentDB explain field glossary, load
> [`references/documentdb-explain-output.md`](references/documentdb-explain-output.md).

## Step 2 — A naive single-field index is not enough

```javascript
db.orders.createIndex({ status: 1 })
```

Now it's an `IXSCAN`, but still **249,800 index keys examined to return 18** — a
low-cardinality field like `status` narrows nothing useful, doesn't help
`customerId` / `createdAt`, and the sort still runs **in memory**
(`scanType: "regular"`, a `SORT` stage above the `IXSCAN`).

## Step 3 — Apply the ESR rule

> **E**quality → **S**ort → **R**ange

| Role | Field(s) |
|---|---|
| **Equality** (`$eq`) | `customerId`, `status` |
| **Sort** | `createdAt` (`-1`) |
| **Range** (`$gte`) | `createdAt` |

`createdAt` is used in both sort and range, so it appears **once**, in the sort
position (walking the index in sort order also satisfies the range).

```javascript
db.orders.createIndex({ customerId: 1, status: 1, createdAt: -1 })
```

**Most selective equality field first.** `customerId` (high cardinality:
thousands of distinct values) skips far more entries than `status` (low
cardinality: `shipped`/`pending`/`cancelled`), so it leads even though it isn't
unique.

Re-run `explain()` → **18 keys examined, 18 returned, 0.058 ms, zero in-memory
sort** (`scanType: "ordered"`, `hasOrderBy: true`, a `FETCH → IXSCAN` plan).

## Step 4 — Confirm the sort is index-backed

Look for the **absence of a `SORT` stage**. Ideal:

```text
FETCH
└── IXSCAN { customerId: 1, status: 1, createdAt: -1 }
```

Not ideal (sort still in memory):

```text
SORT
└── FETCH
    └── IXSCAN { status: 1 }
```

On DocumentDB, also confirm the `IXSCAN` reports `scanType: "ordered"` and
`hasOrderBy: true`.

## Step 5 — Go further with covered queries

Even a perfect `IXSCAN` still does a `FETCH` (index → back to the collection for
the document). A **covered query** puts *every* field the query touches —
filter, sort, **and projection** — in the index, so the engine never reads the
documents (no `FETCH` stage):

```javascript
db.orders.find(
  { status: "shipped", customerId: "C-4821", createdAt: { $gte: ISODate("2024-01-01") } },
  { _id: 0, customerId: 1, status: 1, createdAt: 1 }   // only indexed fields; exclude _id
).sort({ createdAt: -1 }).explain("executionStats")
// winning plan collapses to just IXSCAN — 0.053 ms
```

**Worth it when:** high-read collections where the same query runs thousands of
times/sec and the projected fields are a small subset of a wide document. If you
need the full document anyway, the `FETCH` is unavoidable — don't contort the
projection just to chase coverage.

## Gotchas

- **Top-line explain metrics lie.** `executionTimeMillis` and `totalDocsExamined`
  at the *top* stage can look fine during a full scan — read the nested scan
  stage (see Step 1).
- **Range fields first breaks ESR.** `createIndex({ createdAt: -1, customerId: 1, status: 1 })`
  forces a wide date-range scan before the equality filters apply. Equality first.
- **Mismatched multi-field sort direction.** The sort must match the index fields
  **and directions** exactly, **or** be their complete reverse. Given `{ a: 1, b: -1 }`:
  `sort({ a: 1, b: -1 })` ✅ and `sort({ a: -1, b: 1 })` ✅; `sort({ a: 1, b: 1 })`
  ⚠️ only `a` uses the index and `b` is sorted in memory.
- **Over-indexing.** Every index costs write throughput and storage. Index for
  *actual* query patterns confirmed with `explain()`, not preemptively.

## Quick reference: ESR checklist

Before creating a compound index, answer three questions:

1. Which fields use **exact match** (`$eq`)? → **first** (most selective first).
2. Which field is used in **`sort()`**? → **middle**, matching the sort direction.
3. Which fields use **range operators** (`$gt`, `$lt`, `$gte`, `$lte`, `$in`)? → **last**.

## Summary

| Lever | Effect |
|---|---|
| Diagnostic Logs + Log Analytics (`VCoreMongoRequests`) | Surface slow queries before they become incidents |
| Replace `COLLSCAN` with `IXSCAN` | Eliminate the full collection scan |
| Apply the ESR rule to a compound index | Narrow key scans to near-exact matches |
| Match index direction to the sort | Eliminate the in-memory `SORT` |
| Cover the query with a projection | Eliminate the `FETCH` stage entirely |

## References

- Full DocumentDB explain field glossary + annotated plans: [`references/documentdb-explain-output.md`](references/documentdb-explain-output.md)
- [Query Performance Tuning Guide](https://devblogs.microsoft.com/documentdb/query-performance-tuning-guide/) (devblog)
- [How to read explain output](https://learn.microsoft.com/en-us/azure/documentdb/how-to-read-explain-output)
- [How to monitor diagnostics logs](https://learn.microsoft.com/en-us/azure/documentdb/how-to-monitor-diagnostics-logs)
- Related skills: `documentdb-query-optimizer` (interactive MCP tuning), `documentdb-indexing` (index-type selection), `documentdb-monitoring` (enable diagnostic settings)
