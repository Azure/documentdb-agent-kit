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

1. Use `list_indexes` (MCP) or `db.<coll>.getIndexes()` (mongosh) to get existing indexes on the collection
2. Use `explain_operation` (MCP) or `.explain("executionStats")` (mongosh)
   to get explain output with execution stats
3. Use `find_documents` (MCP) or `db.<coll>.findOne()` (mongosh) to fetch a sample document to understand the
   schema

Then make an optimization suggestion based on collected information and best
practices from the reference files. Prefer creating an index that fully covers
the query if possible.

### General Performance Help

If the user wants to examine slow queries or is looking for general performance
suggestions (not regarding any particular query):

1. Use `list_databases` (MCP) or `show dbs` (mongosh) to understand the database structure
2. Use `get_statistics` with scope "collection" (MCP) or `db.collection.stats()` (mongosh) to identify large collections
3. Use `get_statistics` with scope "index" (MCP) or `db.collection.aggregate([{$indexStats:{}}])` (mongosh) to check existing index usage
4. Use `current_ops` (MCP) or `db.currentOp()` (mongosh) to see currently running operations
5. Suggest reviewing the most-used collections for missing indexes

## MCP Tools Available

When DocumentDB MCP server is connected, these tools are available:

| Tool name (exact) | Description |
| :--- | :--- |
| `list_indexes` | List all indexes on a collection — check if the query can use an existing index |
| `explain_operation` | Run explain with executionStats for any operation (find, aggregate, count) |
| `find_documents` | Fetch sample documents to understand schema — use with limit=1 |
| `get_statistics` | Get collection or index statistics (use scope: "collection" or "index") |
| `current_ops` | Get currently running database operations |
| `create_index` | Create a new index (only after user approval) |
| `drop_index` | Drop an existing index (only after user approval) |
| `sample_documents` | Sample random documents from a collection |

## Local mongosh Commands (No MCP Required)

All diagnostic operations can be performed directly via mongosh. Use these when
MCP is not available or for quick ad-hoc diagnostics:

```javascript
// Explain a find query
db.collection.find({filter}).explain("executionStats")

// Explain an aggregation pipeline
db.collection.aggregate([{$match:...}, {$group:...}]).explain("executionStats")

// Explain a count
db.runCommand({explain: {count: "collection", query: {filter}}, verbosity: "executionStats"})

// Collection statistics
db.collection.stats()

// List indexes
db.collection.getIndexes()

// Index usage statistics
db.collection.aggregate([{$indexStats: {}}])

// Sample documents
db.collection.aggregate([{$sample: {size: 3}}])

// Currently running operations
db.currentOp()
```

## Load References

Before beginning diagnosis and recommendation, load reference files.

Always load:

- `references/core-indexing-principles.md`

## Diagnostic Workflow

### Step 1: Gather Information

For a specific query, run these tools:

**Via MCP (when connected):**
```
list_indexes({ db_name: "<db>", collection_name: "<coll>" })
```

```
explain_operation({
  db_name: "<db>",
  collection_name: "<coll>",
  operation: {
    find: "<coll>",
    filter: <filter>,
    sort: <sort>,
    projection: <projection>,
    limit: <n>
  }
})
```

For aggregation pipelines:
```
explain_operation({
  db_name: "<db>",
  collection_name: "<coll>",
  operation: {
    aggregate: "<coll>",
    pipeline: <pipeline_array>,
    cursor: {}
  }
})
```

**Via mongosh (no MCP):**
```javascript
use <db>
db.<coll>.getIndexes()
db.<coll>.find(<filter>).sort(<sort>).explain("executionStats")
db.<coll>.aggregate(<pipeline>).explain("executionStats")
```

### Step 2: Analyze Explain Output

From the `explain("executionStats")` response (via MCP `explain_operation` or
direct mongosh), extract:

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
2. Re-run `explain_operation` (MCP) or `.explain("executionStats")` (mongosh) with the same query
3. Compare metrics before and after

## Example Workflow

**User:** "Why is this query slow?
`db.orders.find({status: 'shipped', region: 'US'}).sort({date: -1})`"

**If MCP connection is available**, run steps 1–3:

1. **Check existing indexes:**
   - Call `list_indexes` with database=`store`, collection=`orders`
   - Result shows: `{_id: 1}`, `{status: 1}`, `{date: -1}`

2. **Run explain:**
   - Call `explain_operation` with operation=`{find: "orders", filter: {status: "shipped", region: "US"}, sort: {date: -1}}`
   - Result: Uses `{status: 1}` index, then in-memory SORT,
     totalKeysExamined: 50000, nReturned: 100

3. **Fetch sample:**
   - Call `find_documents` with limit=1 to understand the schema

**If MCP is not available**, use mongosh directly:

```javascript
use store
db.orders.getIndexes()
db.orders.find({status: "shipped", region: "US"}).sort({date: -1}).explain("executionStats")
db.orders.findOne()
```

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
