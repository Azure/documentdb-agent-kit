---
name: documentdb-query-optimizer
description: >-
  Help with DocumentDB/MongoDB query optimization and indexing for Azure
  DocumentDB. Use only when the user asks for optimization or
  performance: "How do I optimize this query?", "How do I index this?", "Why is
  this query slow?", "Can you fix my slow queries?", etc. Do not invoke for
  general query writing unless user asks for performance or index help. Prefer
  indexing as optimization strategy. Use DocumentDB MCP when available.
allowed-tools: mcp__documentdb__*
---

# DocumentDB Query Optimizer

## When This Skill Is Invoked

Invoke **only** when the user wants:

- Query/index **optimization** or **performance** help
- **Why** a query is slow or **how to speed it up**
- **Slow queries** on their cluster and/or **how to optimize them**
- Index recommendations or index review

Do **not** invoke for routine query authoring unless the user has requested help
with optimization, slow queries, or indexing.

## High Level Workflow

### Help with a Specific Query

If the user is asking about a particular query:

1. Use `list_indexes` to get existing indexes on the collection
2. Use `optimize_find_query` (for find queries) or `explain_aggregate_query`
   (for aggregation pipelines) to get explain output with execution stats
3. Use `find_documents` with limit=1 to fetch a sample document to understand the
   schema

Then make an optimization suggestion based on collected information and best
practices from the reference files. Prefer creating an index that fully covers
the query if possible.

### General Performance Help

If the user wants to examine slow queries or is looking for general performance
suggestions (not regarding any particular query):

1. Use `list_databases` and `get_db_info` to understand the database structure
2. Use `collection_stats` to identify large collections
3. Use `index_stats` to check existing index usage
4. Use `current_ops` to see currently running operations
5. Suggest reviewing the most-used collections for missing indexes

## MCP Tools Available

**Database tools** (for query optimization):

| Tool name (exact) | Description |
| :--- | :--- |
| `list_indexes` | List all indexes on a collection — check if the query can use an existing index |
| `optimize_find_query` | Run explain with executionStats for a find query, returning metrics, plan shape, index stats, and collection stats in one call |
| `explain_aggregate_query` | Run explain with executionStats for an aggregation pipeline |
| `explain_find_query` | Run explain for a find query (lower-level than optimize_find_query) |
| `explain_count_query` | Run explain for a count query |
| `find_documents` | Fetch sample documents to understand schema — use with limit=1 |
| `collection_stats` | Get collection statistics (size, document count, storage) |
| `index_stats` | Get index usage statistics ($indexStats) |
| `current_ops` | Get currently running database operations |
| `create_index` | Create a new index (only after user approval) |
| `drop_index` | Drop an existing index (only after user approval) |

## Load References

Before beginning diagnosis and recommendation, load reference files.

Always load:

- `references/core-indexing-principles.md`

## Diagnostic Workflow

### Step 1: Gather Information

For a specific query, run these tools (when MCP is connected):

```
list_indexes({ db_name: "<db>", collection_name: "<coll>" })
```

```
optimize_find_query({
  db_name: "<db>",
  collection_name: "<coll>",
  query: <filter>,
  options: { sort: <sort>, projection: <projection>, limit: <n> }
})
```

For aggregation pipelines:
```
explain_aggregate_query({
  db_name: "<db>",
  collection_name: "<coll>",
  pipeline: <pipeline_array>
})
```

### Step 2: Analyze Explain Output

From the `optimize_find_query` / `explain_aggregate_query` response, extract:

- **metrics**: `totalKeysExamined`, `totalDocsExamined`, `nReturned`,
  `executionTimeMillis`
- **plan_shape**: winning plan stage (IXSCAN vs COLLSCAN), index used
- **indexes_stats**: which indexes exist and their usage frequency
- **collection_stats**: total document count, average document size

**Key ratios to evaluate:**

| Metric | Good | Bad |
| :--- | :--- | :--- |
| keysExamined / nReturned | Close to 1 | >> 1 (poor selectivity) |
| docsExamined / nReturned | Close to 1 | >> 1 (scanning too many docs) |
| Plan stage | IXSCAN | COLLSCAN (no index) |
| Sort stage | In-memory: false | In-memory: true (blocking sort) |

### Step 3: Diagnose

Common issues and their root causes:

- **COLLSCAN** → No index supports the query filter. Create an index on
  the filter fields.
- **High keysExamined vs nReturned** → Index exists but has poor selectivity.
  Consider a more selective compound index.
- **In-memory sort** → Sort field is not indexed. Add sort field to the index
  (after equality fields, before range fields).
- **Large docsExamined** → Index doesn't cover the query. Consider a covering
  index that includes projected fields.

### Step 4: Recommend

Follow the **ESR Rule** (Equality → Sort → Range) for compound index design:

1. **Equality** fields first (fields with `$eq` / exact match)
2. **Sort** fields next (fields in the `sort` specification)
3. **Range** fields last (fields with `$gt`, `$lt`, `$gte`, `$lte`, `$in`)

**Example:**
Query: `db.orders.find({status: 'shipped', region: 'US'}).sort({date: -1})`
Recommended index: `{status: 1, region: 1, date: -1}`
(Two equality fields, then sort field)

### Step 5: Verify (Optional)

After creating the recommended index, re-run the explain to confirm improvement:

1. Create the index (with user approval)
2. Re-run `optimize_find_query` with the same query
3. Compare metrics before and after

## Example Workflow

**User:** "Why is this query slow?
`db.orders.find({status: 'shipped', region: 'US'}).sort({date: -1})`"

**If MCP connection is available**, run steps 1–3:

1. **Check existing indexes:**
   - Call `list_indexes` with database=`store`, collection=`orders`
   - Result shows: `{_id: 1}`, `{status: 1}`, `{date: -1}`

2. **Run explain:**
   - Call `optimize_find_query` with query=`{status: 'shipped', region: 'US'}`,
     options=`{sort: {date: -1}}`
   - Result: Uses `{status: 1}` index, then in-memory SORT,
     totalKeysExamined: 50000, nReturned: 100

3. **Fetch sample:**
   - Call `find_documents` with limit=1 to understand the schema

4. **Diagnose:** This query targets 100 docs but scans 50K index entries (poor
   selectivity: 0.002). In-memory sort adds overhead. The `{status: 1}` index
   doesn't support both filter fields or sort.

5. **Recommend:** Create compound index `{status: 1, region: 1, date: -1}`
   following ESR (two equality fields, then sort). This eliminates in-memory
   sort and improves selectivity.

## Azure DocumentDB Specifics

- **Index types supported**: Single field, compound, text, geospatial
  (2dsphere), wildcard, unique
- **Default _id index**: Every collection has an automatic `_id` index
- **Compound index limit**: Check current Azure documentation for maximum
  number of fields in a compound index
- **Index builds**: Index creation on Azure DocumentDB may take time for large collections;
  the operation runs in the background
- **Covered queries**: Azure DocumentDB supports covered queries (index-only scans) when
  all queried and projected fields are in the index
- **Vector search**: Azure DocumentDB supports vector indexes (IVF, HNSW) for similarity
  search. If IVF recall is poor, recommend switching to HNSW.

## Output Format

- Keep answers short and clear: a few sentences on index and optimization
  suggestions, and reasoning behind them
- Focus on highest-impact optimizations first
- Do not use strong language like "You should definitely create these indexes"
  — explain they are suggestions with reasoning
- Consider how many indexes already exist — there shouldn't generally be
  more than 20
- Do not create or drop indexes directly via MCP unless the user gives approval
- Present before/after metrics when possible

## Safety Rules

- **NEVER create or drop indexes without explicit user approval**
- Always explain what the index change will do and why before asking for
  approval
- If the collection has many existing indexes (>15), warn about the overhead of
  adding more
- For drop recommendations, explain the impact on other queries that may use
  the index
