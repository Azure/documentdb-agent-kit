# driver-connection-lifecycle

**Category:** Driver Best Practices · **Priority:** HIGH

## Why it matters

A one-off seed, import, or maintenance script owns a finite connection lifetime.
Leaving its pool or monitoring handles open can keep Node.js running after the
work finishes. **Await cleanup in `finally` on success and failure**, including a
failed connection attempt. This is not permission to close a caller's client or
to create/close clients per request: servers and warm serverless invocations
must [reuse their shared client](driver-singleton-client.md).

## Incorrect

```javascript
await client.connect();
await importRows(client); // If this rejects, close is never reached.
client.close();           // Not awaited.
// process.exit(0) would mask failure and interrupt pending cleanup.
```

Logging an error without a nonzero exit status also makes a failed import look
successful to a shell or deployment job.

## Correct

These are standalone CommonJS script examples using the application's installed
driver/ODM and `DOCUMENTDB_URI`. Each script creates and owns its connection.
The error list preserves an operation failure if cleanup also fails; a cleanup
failure alone still fails the script. `process.exitCode` allows awaited cleanup
to finish without forcing process termination.

### MongoDB Node.js driver

<!-- contract: owned-mongo-script -->
```javascript
const { MongoClient } = require("mongodb");

async function main() {
  const client = new MongoClient(process.env.DOCUMENTDB_URI);
  const errors = [];
  try {
    await client.connect();
    await client.db().collection("events").insertOne({ kind: "seed" });
  } catch (error) {
    errors.push(error);
  } finally {
    try {
      await client.close();
    } catch (error) {
      errors.push(error);
    }
  }
  if (errors.length === 1) throw errors[0];
  if (errors.length > 1) {
    throw new AggregateError(errors, "Operation and cleanup failed", { cause: errors[0] });
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
```

### Mongoose: close the owned connection, not every connection

`createConnection()` returns a connection, not a connection-ready promise.
Keep its reference before awaiting `openUri()` so failure still reaches cleanup.
`connection.close()` closes this owned connection; `mongoose.disconnect()` closes
all connections and is appropriate only when the script owns all of them.

<!-- contract: owned-mongoose-script -->
```javascript
const mongoose = require("mongoose");

async function main() {
  const connection = mongoose.createConnection();
  const errors = [];
  try {
    await connection.openUri(process.env.DOCUMENTDB_URI, { autoIndex: false });
    const Event = connection.model("Event", new mongoose.Schema({ kind: String }));
    await Event.insertMany([{ kind: "seed" }]);
  } catch (error) {
    errors.push(error);
  } finally {
    try {
      await connection.close();
    } catch (error) {
      errors.push(error);
    }
  }
  if (errors.length === 1) throw errors[0];
  if (errors.length > 1) {
    throw new AggregateError(errors, "Operation and cleanup failed", { cause: errors[0] });
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
```

These seeds do not require a secondary index. If an import depends on uniqueness
or another required index, establish
[index readiness](../indexing/index-required-readiness.md) **before** the writes.
For servers, the owner closes the shared connection during graceful shutdown
after stopping new requests and draining in-flight work, not in handler `finally`.

## Verification

The [offline lifecycle contracts](../../testing/lifecycle/README.md) execute these
exact marked snippets with mocks, including real referenced timer handles in
bounded child processes. They check cleanup and exit status, not database behavior.

## References

- [MongoDB Node driver — create/reuse a client and awaited cleanup](https://www.mongodb.com/docs/drivers/node/current/connect/mongoclient/)
- [Mongoose — Connection.openUri](https://mongoosejs.com/docs/api/connection.html#Connection.prototype.openUri()) and [Connection.close](https://mongoosejs.com/docs/api/connection.html#Connection.prototype.close())
- [Mongoose — disconnect closes all connections](https://mongoosejs.com/docs/api/mongoose.html#Mongoose.prototype.disconnect())
