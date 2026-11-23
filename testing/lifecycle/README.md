# Offline connection and index lifecycle contracts

Run from the repository root with Node.js 24.21.0 (the CI pin):

```bash
node --test testing/lifecycle/lifecycle.test.mjs
```

No dependency installation, cloud, Docker, credentials, database, network access,
or model calls are needed. The existing `static` infrastructure-free job in
`diagnostic-regression.yml` runs this command. These tests are not pytest scenarios.

## Source of truth

`snippets.mjs` extracts the exact JavaScript fences following unique `contract`
markers in:

- [`driver-connection-lifecycle.md`](../../skills/driver/driver-connection-lifecycle.md)
  — complete MongoClient and Mongoose one-off scripts, including exit handling.
- [`index-required-readiness.md`](../../skills/indexing/index-required-readiness.md)
  — explicit required-index initialization before an HTTP listener starts.

There is no second implementation of the examples in the tests. The VM only
supplies the mocked dependencies listed for each example; unexpected imports
fail. Mocks are an API-shaped test fixture, **not a MongoDB or Mongoose emulator**.

## Contracts

- Deferred promises hold connection, operation, cleanup, and index build pending.
  Assertions run before resolution, so starting a build is not treated as ready.
- Both one-off scripts await cleanup on success and on connection/operation
  failure. Cleanup failure is nonzero too; dual failures preserve the original
  error as the aggregate cause.
- `script-child.mjs` gives the owned mock connection a **real referenced timer**.
  Cleanup clears it asynchronously. Each child must naturally exit within four
  seconds: zero on success, nonzero on failure, with cleanup completed first.
  A deliberately leaked-handle negative control must time out, demonstrating
  that a settled script promise alone is insufficient. The timeout kills that
  child; the tests do not leave a background worker behind. Close-error cases
  reject after clearing the timer: they test error reporting, not recovery of
  resources left open by a real failed close.
- A declared unique field exists while its build promise is still pending, but
  the listener and dependent query cannot start yet. Success keeps the shared
  connection open across requests and does not rebuild per request.
- Connection, index, simulated existing-duplicate, and listener failures reject
  startup and await owned-connection cleanup. Index failure never enables the
  listener. The fixture has no data-deletion or `syncIndexes()` API.

## Claim boundary

These tests demonstrate **mocked lifecycle ordering and process-exit contracts**.
They do not verify unique-index enforcement, MongoDB/Mongoose wire behavior,
Azure DocumentDB compatibility/build semantics, production migration execution,
or whether an agent follows the skills. A mocked duplicate-data rejection is
not evidence of a database rejecting duplicates. Live service tests and agent
quality evaluations remain separate, explicitly authorized work.
