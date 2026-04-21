# model-embed-vs-reference

**Category:** Data Modeling · **Priority:** CRITICAL

## Why it matters

Cosmos DB for MongoDB vCore rewards designs where data accessed together lives together. Embedding related sub-documents avoids extra round trips and joins (`$lookup`), but unbounded embedding creates 16 MB documents, hot writes, and write amplification. The right choice depends on access pattern, growth, and 1-to-N cardinality.

Rule of thumb:
- **Embed** when the child is always read with the parent, has bounded size, and changes with the parent.
- **Reference** when children grow unbounded (comments, events, audit logs), are accessed independently, or are shared across parents.

## Incorrect

Embedding unbounded arrays in a single document:

```javascript
// orders collection
{
  _id: "user-123",
  name: "Ada",
  orders: [ /* ...could grow to thousands... */ ]
}
```

Over time the document approaches the 16 MB BSON limit, every update rewrites the full array, and queries that only need the user profile pay the cost of loading all orders.

## Correct

Split unbounded N-side into its own collection and reference by id:

```javascript
// users collection
{ _id: "user-123", name: "Ada" }

// orders collection (sharded on userId)
{ _id: ObjectId(...), userId: "user-123", total: 42.00, items: [...] }
```

Embed only when bounded:

```javascript
// products collection — addresses list is tiny and read with the product
{ _id: "sku-1", name: "Widget", suppliers: [{ id: "s1", name: "Acme" }] }
```

## References

- [Data modeling in Azure Cosmos DB for MongoDB vCore](https://learn.microsoft.com/azure/cosmos-db/mongodb/vcore/)
- MongoDB data modeling patterns (embedded vs referenced)
