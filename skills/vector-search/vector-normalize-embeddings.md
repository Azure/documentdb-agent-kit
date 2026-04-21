# vector-normalize-embeddings

**Category:** Vector Search · **Priority:** HIGH

## Why it matters

Cosine similarity (`COS`) compares direction, not magnitude. If your vectors aren't unit-length, `COS` still works mathematically but `IP` (inner product) won't behave like cosine, and sorting by raw dot products will be dominated by vector magnitude rather than semantic closeness. Also, mixing multiple embedding models in one collection without metadata is a common source of silent bugs.

Rules:
- Pick one similarity and use it consistently at ingestion, index, and query time.
- For text embeddings with `COS`, normalize to unit length at ingestion (many providers already do this, e.g. OpenAI text-embedding-3; verify).
- Store the **embedding model name** and **dimensions** alongside the vector so you can detect drift and drive re-embedding jobs.

## Incorrect

```javascript
// Mixing raw vectors (varied magnitudes) with IP similarity
index: { similarity: "IP", dimensions: 1536 }
insert: { embedding: rawFromTwoDifferentModels } // some normalized, some not
// Ranking is distorted by magnitude; top-k is wrong.
```

## Correct

```javascript
// At ingest
const vec = await embed(text, model);
const normalized = normalize(vec); // L2-normalize to unit length

await db.products.insertOne({
  _id,
  title,
  embedding: normalized,
  embeddingModel: "text-embedding-3-small",
  embeddingDims: 1536,
  embeddingVersion: 1
});

// Index
db.products.createIndex(
  { embedding: "cosmosSearch" },
  { cosmosSearchOptions: { kind: "vector-diskann", dimensions: 1536, similarity: "COS" } }
);
```

When you change models or normalization strategy, bump `embeddingVersion` and run a backfill.

## References

- [Vector search concepts](https://learn.microsoft.com/azure/documentdb/vector-search)
- [Understand embeddings (Azure OpenAI)](https://learn.microsoft.com/azure/ai-services/openai/concepts/understand-embeddings)
