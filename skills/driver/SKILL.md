---
name: documentdb-driver
description: MongoDB driver and SDK best practices for Azure DocumentDB — singleton `MongoClient`, connection reuse, connection-pool fundamentals, and owned-client cleanup in seed/import scripts. Use when writing code that instantiates a MongoDB client, reviewing driver initialization, or diagnosing connection-related bugs and scripts that do not exit. For full connection-pool tuning (serverless vs OLTP vs OLAP, timeouts, retries), see the `documentdb-connection` skill.
license: MIT
---

# Driver Best Practices — Azure DocumentDB

MongoDB driver usage patterns that apply across Node.js, Python, Java, Go, and .NET. For in-depth pool-size / timeout / retry tuning, see the `documentdb-connection` skill.

## Rules

- [driver-singleton-client](driver-singleton-client.md) — Reuse `MongoClient` as a process-wide singleton; never create a new client per request.
- [driver-connection-lifecycle](driver-connection-lifecycle.md) — Await cleanup of owned one-off clients on success and failure; preserve shared server clients.
