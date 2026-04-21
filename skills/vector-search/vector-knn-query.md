# vector-knn-query

**Category:** Vector Search · **Priority:** HIGH

## Why it matters

In Azure DocumentDB, kNN searches use the `$search` aggregation stage with the `cosmosSearch` operator. The query vector must match the index's dimensions and similarity. Tune `lSearch` and `k` for the recall/latency tradeoff, and use the optional `filter` field (inside `cosmosSearch`) to push predicates **into** the ANN search — this is far more efficient than post-filtering in a later `$match` stage.

## Incorrect

Using Atlas Vector Search syntax (`$vectorSearch`) — not supported in DocumentDB:

```javascript
db.products.aggregate([
  { $vectorSearch: { index: "vec", path: "embedding", queryVector: qv, numCandidates: 100, limit: 5 } }
]);
```

Or post-filtering that drops 90% of your top-k before the user sees anything:

```javascript
db.products.aggregate([
  { $search: { cosmosSearch: { path: "embedding", query: qv, k: 10 } } },
  { $match: { inStock: true, price: { $lte: 100 } } } // may leave 1-2 results
]);
```

## Correct

Use `cosmosSearch` with pre-filters and return the score:

```javascript
const queryVector = await embed(userQuery);

const hits = await db.products.aggregate([
  {
    $search: {
      cosmosSearch: {
        path: "embedding",
        query: queryVector,
        k: 10,
        lSearch: 100, // higher than k, boosts recall
        filter: {
          $and: [
            { inStock: { $eq: true } },
            { price: { $lte: 100 } }
          ]
        }
      }
    }
  },
  {
    $project: {
      _id: 1, title: 1, price: 1,
      score: { $meta: "searchScore" }
    }
  }
]).toArray();
```

Tips:
- Keep `lSearch >= k`; raise `lSearch` when recall is low.
- Use the `filter` field for geospatial (`$geoWithin`), range, and equality predicates.
- Always project `searchScore` if you plan to rerank or threshold.

## References

- [Vector search queries](https://learn.microsoft.com/azure/documentdb/vector-search)
