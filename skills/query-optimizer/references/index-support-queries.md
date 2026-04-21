# index-support-queries

**Category:** Indexing · **Priority:** HIGH

## Why it matters

Without a supporting index, queries do a **collection scan** (`COLLSCAN`) — CPU, IO, and memory cost grow linearly with collection size, and latency becomes unpredictable. Build compound indexes that match the **Equality, Sort, Range (ESR)** order of your query.

## Incorrect

```javascript
// Query:
db.orders.find({ customerId, status: "open" }).sort({ createdAt: -1 });

// Index:
db.orders.createIndex({ createdAt: -1 }); // only helps sort, still scans for match
```

`explain("executionStats")` shows a large `docsExamined` vs. `nReturned` ratio.

## Correct

```javascript
// Equality fields first, then sort, then range
db.orders.createIndex({ customerId: 1, status: 1, createdAt: -1 });
```

Verify with:

```javascript
db.orders.find({ customerId, status: "open" })
  .sort({ createdAt: -1 })
  .explain("executionStats");
// Expect: stage "IXSCAN", docsExamined ≈ nReturned
```

## References

- MongoDB ESR rule for compound indexes
- [Indexing in Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/)
