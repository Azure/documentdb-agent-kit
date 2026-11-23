# index-required-readiness

**Category:** Indexing · **Priority:** HIGH

## Why it matters

Required indexes are a readiness prerequisite for dependent writes and queries.
Mongoose's `unique: true` declares a unique index; it is **not validation** and
does not mean the build has completed. A connected client, schema declaration,
or index metadata alone is not evidence that a required build completed
successfully. Do not diagnose a broken unique-index engine from operations that
raced initialization; first establish the build outcome and target collection.

## Incorrect

```javascript
const User = connection.model("User", new mongoose.Schema({
  email: { type: String, unique: true }
}));
User.createIndexes().catch(console.error); // Failure is logged, but traffic still starts.
server.listen(3000);                     // Writes/queries can race the build.
```

## Correct

Choose a readiness strategy for the **required** indexes, not every possible
index and not on every request:

- **Automatic development/test initialization:** with `autoIndex` enabled,
  await successful `Model.init()` for each required model before dependent work.
- **Explicit initialization:** with `autoIndex: false`, `Model.init()` alone does
  not build indexes. Await `Model.createIndexes()` (or the Node driver's
  `collection.createIndex()` for a specific required index). A rejected build
  must not enable traffic.
- **Production migration:** prefer a controlled, versioned migration that builds
  the required indexes before rollout. Record successful completion and verify
  the expected keys/options on the correct database/collection before enabling
  dependent traffic. Do not turn on automatic production DDL or rebuild all
  indexes at every application startup. Metadata helps verify the definition;
  it does not replace the migration's successful completion evidence. For APIs
  with asynchronous builds, also wait for their documented ready state.

This minimal CommonJS bootstrap illustrates **explicit development/test
initialization** of an ordinary unique index. It uses a real `node:http` server
bound to loopback with one query route, not a full application. The returned server and
connection belong to the caller, which must handle startup rejection (and set a
nonzero exit status for a failed startup), normal server error handling, and
graceful shutdown. Use your
production migration strategy instead of copying startup DDL into every
production replica.

<!-- contract: required-index-server -->
```javascript
const http = require("node:http");
const mongoose = require("mongoose");

async function startUserApi(uri, port) {
  const connection = mongoose.createConnection();
  try {
    await connection.openUri(uri, { autoIndex: false, autoCreate: false });
    const User = connection.model("User", new mongoose.Schema({
      email: { type: String, required: true, unique: true }
    }, { autoIndex: false, autoCreate: false }));

    await User.createIndexes(); // Required build must succeed before listen.

    const server = http.createServer(async (_req, res) => {
      try {
        res.end(String(await User.countDocuments()));
      } catch {
        res.statusCode = 500;
        res.end("Query failed");
      }
    });
    await new Promise((resolve, reject) => {
      server.once("error", reject);
      server.listen(port, "127.0.0.1", () => {
        server.removeListener("error", reject);
        resolve();
      });
    });
    return { server, connection }; // Reuse until owner-managed shutdown.
  } catch (error) {
    try {
      await connection.close();
    } catch (closeError) {
      throw new AggregateError([error, closeError], "Startup and cleanup failed", { cause: error });
    }
    throw error;
  }
}

module.exports = { startUserApi };
```

Starting the listener only after readiness is one option. If infrastructure
requires an earlier listener, keep readiness false and return **503** for all
dependent writes/queries until initialization succeeds. Background consumers and
seeders need the same gate. A fixed sleep or a logged-and-ignored build error is
not a gate.

**Fail closed:** existing duplicates can cause a unique-index build to fail.
Keep dependent traffic disabled, surface the error, and require an operator-led
data remediation/migration decision. Do not automatically delete duplicates or
use `syncIndexes()` as a readiness shortcut: it can drop indexes absent from the
schema. Do not close a borrowed/shared connection from an initialization helper;
the example closes only the connection it creates when startup fails.

## Verification

[Offline lifecycle contracts](../../testing/lifecycle/README.md) execute the
exact marked bootstrap with deferred mock connection/build/cleanup promises.
They prove ordering and failure propagation, **not** Azure DocumentDB unique
enforcement, service-specific build semantics, or agent efficacy. Live enforcement
verification requires a separately authorized test against the intended database
after successful initialization.

## References

- [Mongoose — unique is not a validator](https://mongoosejs.com/docs/validation.html#the-unique-option-is-not-a-validator)
- [Mongoose — Model.init](https://mongoosejs.com/docs/api/model.html#Model.init()) and [Model.createIndexes](https://mongoosejs.com/docs/api/model.html#Model.createIndexes())
- [Mongoose — autoIndex](https://mongoosejs.com/docs/guide.html#autoIndex) and [syncIndexes caveats](https://mongoosejs.com/docs/api/model.html#Model.syncIndexes())
- [MongoDB Node driver — indexes](https://www.mongodb.com/docs/drivers/node/current/indexes/)
