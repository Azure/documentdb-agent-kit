# model-16mb-limit

**Category:** Data Modeling · **Priority:** CRITICAL

## Why it matters

BSON documents in Cosmos DB for MongoDB vCore have a hard **16 MB** ceiling. Hitting it causes writes to fail, and documents approaching the limit degrade every read/write — the entire document is transferred and rewritten on each update. Plan for the **steady-state maximum size**, not today's size.

## Incorrect

```javascript
// Appending events forever to a single session doc
await sessions.updateOne(
  { _id: sessionId },
  { $push: { events: newEvent } } // grows unbounded
);
```

## Correct

Cap arrays and spill over to a child collection, or store each event as its own document:

```javascript
// events collection, sharded on sessionId
await events.insertOne({
  sessionId,
  ts: new Date(),
  type: "click",
  payload: {...}
});

// Optionally materialize a rolling summary on the session doc:
await sessions.updateOne(
  { _id: sessionId },
  {
    $push: { recentEvents: { $each: [newEvent], $slice: -50 } },
    $inc: { totalEvents: 1 }
  }
);
```

## References

- [BSON document size limit](https://www.mongodb.com/docs/manual/reference/limits/#mongodb-limit-BSON-Document-Size)
- [Cosmos DB for MongoDB vCore limits](https://learn.microsoft.com/azure/cosmos-db/mongodb/vcore/limits)
