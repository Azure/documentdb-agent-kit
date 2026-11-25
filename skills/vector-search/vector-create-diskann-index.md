# vector-create-diskann-index

**Category:** Vector Search · **Priority:** HIGH

## Why it matters

DiskANN is the recommended vector index in Azure DocumentDB for production-scale workloads. Its `maxDegree`, `lBuild`, and the query-time `lSearch` parameters trade off build time, memory, recall, and query latency. The `dimensions` and `similarity` values **must match** the embeddings you insert — mismatches produce wrong results silently.

> ### ⚠️ Driver-safety: use `db.command(...)`, not `collection.createIndex(...)`
>
> The typed `createIndex` wrappers in the official **Node.js**, **PyMongo (sync `create_index`)**, and **.NET** drivers serialize against a fixed `IndexDescription` / `CreateIndexOptions` schema and **silently drop unknown option keys** — including `cosmosSearchOptions`. The wire message goes out without it, the server creates a plain B-tree index on the embedding field, and your app falls back to brute-force scans with **no error**. Upgrading the driver does not fix this; it is a typed-API limitation, not a bug.
>
> `mongosh` works because the shell forwards arbitrary keys straight to the underlying `createIndexes` command. To get the same behavior from a driver, bypass the typed wrapper and issue the raw command via `db.command(...)` (Node / PyMongo) or `RunCommand` (.NET). See the per-driver examples below.

Parameter guide:

| Parameter | Range | Default | Notes |
|---|---|---|---|
| `dimensions` | 1–16,000 (with PQ) | — | Must match embedding model output exactly |
| `similarity` | `COS`, `L2`, `IP` | — | Use `COS` for normalized text embeddings |
| `maxDegree` | 20–2048 | 32 | Higher → better recall, more memory / slower build |
| `lBuild` | 10–500 | 50 | Higher → better index quality, slower build |
| `lSearch` (query-time) | 10–1000 | 40 | Higher → better recall, slower queries; must be ≥ `k` |

## Incorrect

### Wrong dimensions vs. the embedding model — silently-incorrect results

```javascript
db.products.createIndex(
  { embedding: "cosmosSearch" },
  { cosmosSearchOptions: { kind: "vector-diskann", dimensions: 768, similarity: "L2" } }
);
// ...but the app uses 1536-dim OpenAI text-embedding-3-small with cosine similarity.
```

### Using the Node.js / PyMongo typed `createIndex` wrapper — silently creates a plain index

```javascript
// Node.js driver — DO NOT use for cosmosSearch indexes.
// The driver's IndexDescription type strips `cosmosSearchOptions`
// before sending. No error is raised. The resulting index is NOT a
// vector index, and queries fall back to brute-force scans.
await db.collection("products").createIndex(
  { embedding: "cosmosSearch" },
  {
    name: "products_embedding_diskann",
    cosmosSearchOptions: {              // ← dropped on the wire
      kind: "vector-diskann",
      dimensions: 1536,
      similarity: "COS"
    }
  }
);
```

```python
# PyMongo sync — same problem. `create_index` ignores cosmosSearchOptions.
db.products.create_index(
    [("embedding", "cosmosSearch")],
    name="products_embedding_diskann",
    cosmosSearchOptions={"kind": "vector-diskann", "dimensions": 1536,
                         "similarity": "COS"},
)
```

## Correct

### `mongosh` (or any shell that forwards unknown keys)

```javascript
db.products.createIndex(
  { embedding: "cosmosSearch" },
  {
    name: "products_embedding_diskann",
    cosmosSearchOptions: {
      kind: "vector-diskann",
      dimensions: 1536,       // matches text-embedding-3-small
      similarity: "COS",      // matches the query-time similarity
      maxDegree: 32,
      lBuild: 50
    }
  }
);
```

### Node.js driver — use `db.command({ createIndexes, ... })`

```javascript
await db.command({
  createIndexes: "products",
  indexes: [
    {
      name: "products_embedding_diskann",
      key: { embedding: "cosmosSearch" },
      cosmosSearchOptions: {
        kind: "vector-diskann",
        dimensions: 1536,
        similarity: "COS",
        maxDegree: 32,
        lBuild: 50
      }
    }
  ]
});
```

### PyMongo — same shape via `db.command(...)`

```python
db.command({
    "createIndexes": "products",
    "indexes": [
        {
            "name": "products_embedding_diskann",
            "key": {"embedding": "cosmosSearch"},
            "cosmosSearchOptions": {
                "kind": "vector-diskann",
                "dimensions": 1536,
                "similarity": "COS",
                "maxDegree": 32,
                "lBuild": 50,
            },
        }
    ],
})
```

### .NET driver — use `IMongoDatabase.RunCommand`

```csharp
var cmd = new BsonDocument
{
    { "createIndexes", "products" },
    { "indexes", new BsonArray
        {
            new BsonDocument
            {
                { "name", "products_embedding_diskann" },
                { "key", new BsonDocument("embedding", "cosmosSearch") },
                { "cosmosSearchOptions", new BsonDocument
                    {
                        { "kind", "vector-diskann" },
                        { "dimensions", 1536 },
                        { "similarity", "COS" },
                        { "maxDegree", 32 },
                        { "lBuild", 50 },
                    }
                }
            }
        }
    }
};
await db.RunCommandAsync<BsonDocument>(cmd);
```

If you change embedding models, **rebuild the index** — mixing dimensions or similarities corrupts results.

## Verifying the index was actually created as a vector index

Because the typed-wrapper failure is silent, always verify the index shape right after creation:

```javascript
db.products.getIndexes()
  .find(i => i.name === "products_embedding_diskann");
// Expect the result to include a `cosmosSearchOptions` block with
// `kind: "vector-diskann"`. If that block is missing, the driver
// dropped it — re-create via `db.command(...)` above.
```

## References

- [Vector search — DiskANN index creation](https://learn.microsoft.com/azure/documentdb/vector-search)
- [MongoDB `createIndexes` command](https://www.mongodb.com/docs/manual/reference/command/createIndexes/)

