# model-denormalize-reads

**Category:** Data Modeling · **Priority:** HIGH

## Why it matters

`$lookup` across sharded collections in vCore can be expensive, especially when the right-side collection is large or not co-located on the shard key. For read-heavy workloads, **duplicate the fields you need on the read path** so a single query on one shard returns everything.

## Incorrect

```javascript
// Every order-list page triggers a $lookup into users
orders.aggregate([
  { $match: { status: "open" } },
  { $lookup: { from: "users", localField: "userId", foreignField: "_id", as: "user" } }
]);
```

## Correct

Copy the small, slow-changing user fields into each order at write time:

```javascript
// On order creation
await orders.insertOne({
  _id, userId, status: "open",
  userSnapshot: { name: user.name, tier: user.tier }, // denormalized
  items, total
});

// Reads need no $lookup
orders.find({ status: "open" }, { projection: { userSnapshot: 1, total: 1 } });
```

Update the snapshot with a change-feed-style process (or scheduled job) when the source user changes, accepting eventual consistency.

## References

- [Modeling for read-heavy workloads](https://learn.microsoft.com/azure/cosmos-db/mongodb/vcore/)
