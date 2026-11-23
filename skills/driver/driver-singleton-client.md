# driver-singleton-client

**Category:** Driver Best Practices · **Priority:** HIGH

## Why it matters

`MongoClient` is thread-safe and owns the connection pool, SDAM topology monitor, and TLS handshakes. Creating a new client per request floods the cluster with handshakes, exhausts ephemeral ports, and increases tail latency. Use **one client per process**, shared across the app.

## Incorrect

```javascript
// Express handler — new client every request
app.get("/users/:id", async (req, res) => {
  const client = new MongoClient(uri); // 🔥
  await client.connect();
  const user = await client.db().collection("users").findOne({ _id: req.params.id });
  await client.close();
  res.json(user);
});
```

## Correct

```javascript
// Module-level singleton
const client = new MongoClient(uri, { maxPoolSize: 50, retryWrites: true });
const clientPromise = client.connect(); // awaited once

app.get("/users/:id", async (req, res) => {
  await clientPromise;
  const user = await client.db().collection("users").findOne({ _id: req.params.id });
  res.json(user);
});
```

Serverless (Azure Functions, Lambda): cache the client on the global/module scope so it survives warm invocations; create it lazily on first use.

One-off seed/import scripts have a different lifetime: close their owned client
in an awaited `finally`, including on failure. See
[driver-connection-lifecycle](driver-connection-lifecycle.md); do not apply that
cleanup per request to the shared client above.

## References

- [MongoDB Node driver — connection management](https://www.mongodb.com/docs/drivers/node/current/fundamentals/connection/)
