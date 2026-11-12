# index-keyset-pagination

**Category:** Indexing · **Priority:** HIGH

## Why it matters

An interaction-history API needs a deterministic order when multiple events share a timestamp. A unique tie-breaker and a matching lexicographic cursor avoid dropping tied events between pages. This is **live keyset pagination**, not a snapshot of a changing collection. Index existence alone does not prove that the engine avoids a sort.

## Incorrect

```javascript
// A timestamp-only boundary skips remaining records with that same timestamp.
collection.find({ customerId, timestamp: { $lt: beforeTimestamp } })
  .sort({ timestamp: -1 })
  .limit(limit);
```

Also incorrect: “New events always appear before the cursor, so later pages cannot change.” An event inserted later can carry a backdated timestamp below the cursor and appear on a subsequent page.

## Correct

Use a unique tie-breaker and preserve the route's customer scope on every page. This example assumes validated `customerId` and limit, and either no cursor or a cursor with **both** a `Date` timestamp and an `ObjectId` id. Decode/validate untrusted cursor input before calling it; never merge a caller-supplied filter object into this filter. See [API input validation](../driver/driver-validate-api-inputs.md).

<!-- executable-example: history-filter -->
```javascript
function historyFilter(customerId, cursor) {
  const filter = { customerId };
  if (cursor) {
    filter.$or = [
      { timestamp: { $lt: cursor.timestamp } },
      { timestamp: cursor.timestamp, _id: { $lt: cursor.id } }
    ];
  }
  return filter;
}
```

Fetch one extra record to detect a next page; construct its boundary from the **last returned record**, not from the extra record:

<!-- executable-example: history-page -->
```javascript
async function historyPage(collection, customerId, cursor, limit) {
  const docs = await collection.find(historyFilter(customerId, cursor))
    .sort({ timestamp: -1, _id: -1 })
    .limit(limit + 1)
    .toArray();
  const hasMore = docs.length > limit;
  const items = docs.slice(0, limit);
  const last = items[items.length - 1];
  const nextCursor = hasMore ? { timestamp: last.timestamp, id: last._id } : null;
  return { items, nextCursor };
}
```

Serialize the cursor using the application's documented format. On continuation, validate both fields and keep all supported customer/channel/time filters in the query. A value-boundary cursor does not grant authorization; enforce access controls separately in a production service. Accepting another customer's boundary does not itself leak data when the route still scopes the query, though the API can reject scope-mismatched cursors for clarity.

### Describe concurrent inserts accurately

- On an **unchanged dataset**, traversal returns each matching record once, including timestamp ties.
- Newly inserted records above the current boundary are not revisited during the current walk; restart from the first page to see them.
- Newly inserted, backdated records below the boundary **may appear on later pages**. Deletions and updates of sort keys can also change the walk.
- Do not promise snapshot consistency or exactly-once traversal over arbitrary concurrent mutations unless the application implements and validates that stronger contract.

### Verify the index and target engine

Start with the workload's customer/time index and inspect the actual `explain("executionStats")` output for the full `{ timestamp: -1, _id: -1 }` sort. A customer/time index may still need a sort for the tie-breaker. Consider an index matching all filter/sort fields only after checking the target's supported index shapes and observed plan; do not claim “no SORT” merely from declaring an index. See [compound ESR design](index-compound-esr.md).

## Verification

Use out-of-order synthetic events for two customers with repeated timestamps. Traverse with page sizes `1`, `7`, and a size larger than the fixture; compare the exact ID union, ordering and duplicates to an independent oracle. Reuse a cursor across customer routes and verify the query never widens scope. Insert a backdated event between pages and confirm the documented live-pagination behavior. Keep local DocumentDB and managed Azure validation claims separate.

## References

- [Azure DocumentDB indexing](https://learn.microsoft.com/azure/documentdb/indexing)
- [MongoDB range-based pagination](https://www.mongodb.com/docs/manual/reference/method/cursor.skip/#using-range-queries)
- [MongoDB sort consistency](https://www.mongodb.com/docs/manual/reference/method/cursor.sort/#sort-consistency)
