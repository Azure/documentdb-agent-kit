---
name: documentdb-driver
description: MongoDB driver and SDK best practices for Azure DocumentDB — singleton `MongoClient`, connection reuse, connection-pool fundamentals, and API input validation before queries or writes. Use when writing a database-backed API, validating pagination or seed inputs, reviewing driver initialization, or diagnosing connection-related bugs. For full connection-pool tuning (serverless vs OLTP vs OLAP, timeouts, retries), see the `documentdb-connection` skill.
license: MIT
---

# Driver Best Practices — Azure DocumentDB

MongoDB driver usage patterns that apply across Node.js, Python, Java, Go, and .NET. For in-depth pool-size / timeout / retry tuning, see the `documentdb-connection` skill.

## Rules

- [driver-singleton-client](driver-singleton-client.md) — Reuse `MongoClient` as a process-wide singleton; never create a new client per request.
- [driver-validate-api-inputs](driver-validate-api-inputs.md) — Reject invalid scalar/count/date/cursor inputs before database I/O; default only omitted fields and preserve safe parser 4xx responses.
