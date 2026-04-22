# Core Indexing Principles for Azure DocumentDB

> Reference doc for the `documentdb-query-optimizer` skill. Load this before
> diagnosing slow queries or recommending new indexes.
>
> Source: [Azure DocumentDB Overview](https://learn.microsoft.com/en-us/azure/documentdb/overview),
> [MQL Compatibility](https://learn.microsoft.com/en-us/azure/documentdb/compatibility-query-language)

## Why Indexes Matter

Without a supporting index, every query does a **collection scan**
(`COLLSCAN`) — CPU, I/O, and memory costs grow linearly with collection size.
A good index turns a linear scan into a logarithmic lookup.

But indexes aren't free:
- Every write updates every relevant index (write amplification).
- Each index takes disk and memory (working-set pressure).
- Too many indexes can make the planner pick a worse plan.

**Rule of thumb:** keep the index count per collection well under 20. Drop
unused indexes (check with `$indexStats` / `index_stats`).

## Supported Index Types

Azure DocumentDB supports the standard MongoDB index types:

| Type | When to use |
|---|---|
| **Single field** | Basic filters on one field |
| **Compound** | Multi-field filters, filter+sort, filter+sort+range |
| **Multikey** | Arrays (created implicitly when a field is an array) |
| **Text** (`createSearchIndexes`) | Full-text search via the `$search` aggregation stage (separate from `createIndex`) |
| **Geospatial** (`2dsphere`) | `$near`, `$geoWithin`, `$geoIntersects` |
| **Wildcard** | Unknown / dynamic field names |
| **Unique** | Enforce uniqueness |
| **TTL** | Auto-expire documents after N seconds |
| **Vector** (`cosmosSearch`) | Similarity search with DiskANN / HNSW / IVF |

Every collection automatically has an `_id` index.

## The ESR Rule (Equality, Sort, Range)

When designing a compound index, order fields as:

1. **Equality** — fields with `$eq` / exact match
2. **Sort** — fields in the `sort()` specification
3. **Range** — fields with `$gt`, `$lt`, `$gte`, `$lte`, `$in`, `$ne`

### Example

Query:
```javascript
db.orders.find({ status: "shipped", region: "US", total: { $gt: 100 } })
         .sort({ createdAt: -1 });
```

Recommended index:
```javascript
db.orders.createIndex({ status: 1, region: 1, createdAt: -1, total: 1 });
//                     └─ equality ──┘  └─ sort ─┘  └ range ┘
```

Why each position matters:
- Equality fields at the prefix narrow the index scan tightly.
- A sort field that immediately follows the equality prefix lets the index
  provide already-sorted results (no blocking in-memory sort).
- Range fields go last because they expand into a range of index keys — any
  equality or sort field placed after a range field cannot use the index.

### Sort direction

For a single sort field, direction doesn't matter — an index on
`{ createdAt: 1 }` can serve `sort({ createdAt: -1 })` by scanning backwards.

For **multi-field sorts**, the index direction must match the sort direction
(or be the exact inverse). `{ a: 1, b: -1 }` serves `sort({ a: 1, b: -1 })` or
`sort({ a: -1, b: 1 })`, but **not** `sort({ a: 1, b: 1 })`.

## Reading `explain("executionStats")`

The planner output is your ground truth. Key fields:

| Field | What it means | Good |
|---|---|---|
| `stage` (winning plan) | `IXSCAN` = index scan, `COLLSCAN` = full scan, `FETCH` = load document after index | `IXSCAN` |
| `indexName` | Which index was used | A purpose-built compound index, not a wildcard |
| `totalKeysExamined` | Index entries visited | Close to `nReturned` |
| `totalDocsExamined` | Documents loaded | Close to `nReturned` |
| `nReturned` | Documents returned | — |
| `executionTimeMillis` | Wall-clock time | Low and stable |
| `SORT` stage present? | Blocking in-memory sort | Absent (sort served by index) |

### Diagnostic ratios

- `totalKeysExamined / nReturned` — selectivity of the index. Should be close
  to 1. Much higher means the index is matching many keys that are later
  filtered out; consider a more selective compound index.
- `totalDocsExamined / nReturned` — how many documents the engine had to fetch
  to satisfy the query. Close to 1 is ideal. Equal to `totalKeysExamined`
  typically means a **covered query** is not happening — the engine is
  fetching docs to resolve projection or unsupported fields.

### Covered queries

If the index contains every field referenced by the filter, sort, and
projection, the planner can satisfy the query **without loading documents at
all** — this is a covered query (`FETCH` stage absent, `totalDocsExamined = 0`).

Covered queries are dramatically cheaper. They require:
- Every field in `filter`, `sort`, and `projection` is in the index.
- `_id` is explicitly excluded from the projection (or included in the index),
  since `_id` is returned by default.

```javascript
db.orders.createIndex({ customerId: 1, status: 1, total: 1 });

db.orders.find(
  { customerId: "c1", status: "open" },
  { _id: 0, total: 1 }          // explicitly exclude _id
).explain("executionStats");    // FETCH stage absent → covered
```

## Common Diagnoses

| Symptom in explain | Likely root cause | Fix |
|---|---|---|
| `COLLSCAN` in winning plan | No index supports the filter | Create an index following ESR |
| Blocking `SORT` stage | Sort field not indexed (or wrong position) | Move sort field right after the equality prefix |
| High `keysExamined / nReturned` | Index prefix not selective enough | Prepend a more selective equality field |
| High `docsExamined / nReturned` with low `keysExamined` | Not a covered query; projection needs a field outside the index | Add the projected field to the index, or exclude it |
| `IXSCAN` but slow | Large working set; index may not fit in memory | Scale tier / drop unused indexes to reclaim memory |

## Indexing Anti-Patterns

- **Indexing every field "just in case"** — write amplification; planner
  confusion. Index only fields you actually filter, sort, or enforce on.
- **Overlapping compound indexes** — `{a:1}` is redundant if `{a:1, b:1}`
  already exists and is used for your `a`-only queries.
- **Indexing low-cardinality booleans alone** — `{active: 1}` where half the
  collection matches isn't selective enough to help. Combine with a more
  selective field.
- **`$where` / JavaScript expressions** — cannot use indexes.
- **`$text` without a text index** — errors; create a `textSearch` index first
  (see `full-text-search/` rules).
- **Ignoring `$indexStats`** — indexes with zero hits in weeks are candidates
  for removal.

## Index Build Behaviour

- Index creation on large collections runs in the **background** on Azure
  DocumentDB; writes continue during the build.
- Progress can be monitored with `current_ops` (via MCP) or
  `db.currentOp({ "command.createIndexes": { $exists: true } })`.
- Keep an eye on disk headroom — a large compound index can be tens of GB.

## Special Index Categories

### Text (`createSearchIndexes`)

Full-text search uses a dedicated search index created with the
`createSearchIndexes` database command and queried through the
`$search` aggregation stage — **not** `createIndex({ field: "text" })`
and **not** the community `$text` operator. See the
`full-text-search/` rules for syntax, custom analyzers (edgeGram,
pathHierarchy), scoring, fuzzy, and phrase operators.

### Vector (`cosmosSearch`)

Vector indexes are declared with the `cosmosSearch` key type. Choose by scale:

| Index type | Scale sweet spot |
|---|---|
| `vector-diskann` (recommended) | Up to 500k+ vectors, M30+ tier |
| `vector-hnsw` | Up to ~50k vectors |
| `vector-ivf` | Under ~10k vectors |

If IVF recall is poor, switch to HNSW or DiskANN. See `vector-search/` rules
for index creation, query syntax, product quantization, and half-precision
indexing.

### TTL

TTL indexes auto-expire documents after a configured age. Useful for session
data, audit logs, feature flags.

```javascript
db.sessions.createIndex({ createdAt: 1 }, { expireAfterSeconds: 3600 });
```

## Verification Workflow

1. **Before:** Run `explain("executionStats")` and record `stage`,
   `totalKeysExamined`, `totalDocsExamined`, `nReturned`, `executionTimeMillis`.
2. **Propose** an index following ESR, and explain why it fits the query.
3. **Get user approval** before creating the index.
4. **Create** the index and wait for the background build to finish.
5. **After:** Re-run the same explain. Expect `IXSCAN`, no blocking `SORT`,
   and `keysExamined ≈ docsExamined ≈ nReturned`.
6. **Monitor** with `$indexStats` over the following week; drop the index if
   unused.

## References

- MongoDB documentation: [Indexes](https://www.mongodb.com/docs/manual/indexes/),
  [ESR rule](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-rule/),
  [`explain` results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- Azure DocumentDB: [Overview](https://learn.microsoft.com/azure/documentdb/),
  [MQL compatibility](https://learn.microsoft.com/azure/documentdb/compatibility-query-language)
