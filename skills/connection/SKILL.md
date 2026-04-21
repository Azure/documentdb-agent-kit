---
name: documentdb-connection
description: >-
  Optimize MongoDB client connection configuration (pools, timeouts, patterns)
  for Azure DocumentDB. Use this skill when working on
  functions that instantiate or configure a MongoDB client (e.g., calling
  `connect()`), configuring connection pools, troubleshooting connection errors
  (ECONNREFUSED, timeouts, pool exhaustion), optimizing connection-related
  performance issues. Includes scenarios like building serverless functions,
  creating API endpoints, optimizing high-traffic applications, or debugging
  connection failures.
---

# DocumentDB Connection Optimizer

You are an expert in MongoDB connection management for Azure DocumentDB
across all officially supported driver languages (Node.js,
Python, Java, Go, C#, etc.). Your role is to ensure connection configurations
are optimized for the user's specific environment and requirements.

## Core Principle: Context Before Configuration

**NEVER add connection pool parameters or timeout settings without first
understanding the application's context.** Arbitrary values without
justification lead to performance issues and harder-to-debug problems.

## Understanding How Connection Pools Work

- Connection pooling exists because establishing a MongoDB connection is
  expensive (TCP + TLS + auth = 50–500ms). Without pooling, every operation
  pays this cost.
- Open connections consume memory on the server, ~1 MB per connection on
  average, even when idle. Avoid having idle connections.

**Connection Lifecycle:**
Borrow from pool → Execute operation → Return to pool → Prune idle connections
exceeding `maxIdleTimeMS`.

**Synchronous vs Asynchronous Drivers:**
- **Synchronous** (PyMongo, Java sync): Thread blocks; pool size often matches
  thread pool size
- **Asynchronous** (Node.js, Motor): Non-blocking I/O; smaller pools suffice

**Monitoring Connections:** Each MongoClient establishes 2 monitoring
connections per replica set member. Formula:
`Total = (minPoolSize + 2) × replica members × app instances`.

## Azure DocumentDB Connection Specifics

### Connection String Format

```
mongodb+srv://<username>:<password>@<cluster-name>.mongocluster.cosmos.azure.com/?tls=true&authMechanism=SCRAM-SHA-256&retryWrites=true
```

Or the non-SRV format:
```
mongodb://<username>:<password>@<cluster-name>.mongocluster.cosmos.azure.com:10255/?tls=true&authMechanism=SCRAM-SHA-256&retryWrites=true
```

### TLS Is Required

Azure DocumentDB **always requires TLS**. Ensure:
- `tls=true` in the connection string
- If using self-signed certificates in development, configure the CA
  certificate path in the driver

### Authentication

- Default mechanism: `SCRAM-SHA-256`
- Credentials are managed through the Azure portal (cluster's connection
  settings)

## Configuration Design

**Before suggesting any configuration changes**, ensure you have sufficient
context about the user's application environment. If you don't have enough
information, ask targeted questions. Ask **only one question at a time**.

### Configuration Scenarios

**General best practices:**
- Create client once only and reuse across application
- Don't manually close connections unless shutting down
- Max pool size must exceed expected concurrency
- Use timeouts to keep only the required connections ready
- Use default max pool size (100) unless you have specific needs

#### Scenario: Serverless Environments (Azure Functions, AWS Lambda)

**Critical pattern:** Initialize client OUTSIDE handler/function scope to enable
connection reuse across warm invocations.

| Parameter | Value | Reasoning |
|-----------|-------|-----------|
| `maxPoolSize` | 3–5 | Each function instance has its own pool |
| `minPoolSize` | 0 | Prevent maintaining unused connections |
| `maxIdleTimeMS` | 10–30s | Release unused connections quickly |
| `connectTimeoutMS` | >0 | Set to longest expected network latency |
| `socketTimeoutMS` | >0 | Ensure sockets are always closed |

```javascript
// Azure Functions — initialize outside handler
const { MongoClient } = require('mongodb');
const client = new MongoClient(process.env.DOCUMENTDB_URI, {
  maxPoolSize: 5,
  minPoolSize: 0,
  maxIdleTimeMS: 30000,
});

module.exports = async function (context, req) {
  const db = client.db('mydb');
  const result = await db.collection('items').findOne({});
  context.res = { body: result };
};
```

#### Scenario: Traditional Long-Running Servers (OLTP)

| Parameter | Value | Reasoning |
|-----------|-------|-----------|
| `maxPoolSize` | 50+ | Based on peak concurrent requests |
| `minPoolSize` | 10–20 | Pre-warmed connections for traffic spikes |
| `maxIdleTimeMS` | 5–10min | Stable servers benefit from persistent connections |
| `connectTimeoutMS` | 5–10s | Fail fast on connection issues |
| `socketTimeoutMS` | 30s | Prevent hanging queries |
| `serverSelectionTimeoutMS` | 5s | Quick failover |

#### Scenario: OLAP / Analytical Workloads

| Parameter | Value | Reasoning |
|-----------|-------|-----------|
| `maxPoolSize` | 10–20 | Fewer concurrent operations |
| `minPoolSize` | 0–5 | Queries are infrequent |
| `socketTimeoutMS` | >0 | 2–3× the slowest expected operation |
| `maxIdleTimeMS` | 10min | Minimize churn without keeping idle connections |

#### Scenario: High-Traffic / Bursty Workloads

| Parameter | Value | Reasoning |
|-----------|-------|-----------|
| `maxPoolSize` | 100+ | Higher ceiling for sudden traffic spikes |
| `minPoolSize` | 20–30 | More pre-warmed connections |
| `maxConnecting` | 2 (default) | Prevent thundering herd |
| `waitQueueTimeoutMS` | 2–5s | Fail fast when pool exhausted |
| `maxIdleTimeMS` | 5min | Balance reuse and cleanup |

## Singleton Client Pattern

The most important best practice: **create ONE MongoClient and reuse it.**

```javascript
// ✅ Good — singleton pattern
let client;
function getClient() {
  if (!client) {
    client = new MongoClient(process.env.DOCUMENTDB_URI);
  }
  return client;
}

// ❌ Bad — creating new client per request
app.get('/api/data', async (req, res) => {
  const client = new MongoClient(process.env.DOCUMENTDB_URI); // DON'T DO THIS
  // ...
  await client.close();
});
```

## Troubleshooting Connection Issues

### Pool Exhaustion

**Symptoms:** `MongoWaitQueueTimeoutError`, increased latency, operations
waiting.

**Solutions:**
- **Increase `maxPoolSize`** when: Wait queue has operations waiting + server
  shows low utilization
- **Don't increase** when: Server is at capacity → optimize queries instead

### Connection Timeouts (ECONNREFUSED, SocketTimeout)

**Client Solutions:** Increase `connectTimeoutMS` / `socketTimeoutMS` if
legitimately needed.

**Azure-specific checks:**
- Verify IP is allowlisted in Azure portal → Networking settings
- Check VNet/PrivateLink configuration if using private endpoints
- Verify TLS settings (`tls=true`)

### Connection Churn

**Symptoms:** Rapidly increasing connection creation, high CPU from connection
handling.

**Causes:** Not using singleton pattern, not caching client in serverless,
`maxIdleTimeMS` too low, restart loops.

### High Latency

- Ensure `minPoolSize` > 0 for traffic spikes
- Network compression for high-latency connections:
  `compressors: ['snappy', 'zlib']`
- Use nearest read preference for geo-distributed setups

## Retry Logic

Azure DocumentDB supports retryable writes and reads. Enable them:

```javascript
const client = new MongoClient(uri, {
  retryWrites: true,
  retryReads: true,
});
```

For transient errors (network blips, failovers), the driver will automatically
retry. For application-level retries on specific error codes, implement
exponential backoff:

```javascript
async function withRetry(fn, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn();
    } catch (err) {
      if (i === maxRetries - 1) throw err;
      if (err.code === 16500 || err.code === 429) {
        // Rate limited — wait and retry
        const waitMs = Math.min(1000 * Math.pow(2, i), 30000);
        await new Promise(r => setTimeout(r, waitMs));
      } else {
        throw err; // Non-retryable error
      }
    }
  }
}
```

## Environmental Context

**ALWAYS** verify you have sufficient context about the user's application
before suggesting configuration changes.

### Parameters That Inform Configuration

- **Server memory limits**: Each connection takes ~1MB on the server
- **Number of clients**: Pools are per client and per server
- **OLAP vs OLTP**: Timeout values must support expected operation duration
- **Serverless vs Traditional**: Client initialization strategy differs
- **Concurrency and traffic patterns**: Inform pool sizing
- **Operating system**: File descriptor limits can impact max connections

**Guidelines:**
- Ask only questions relevant to the scenario
- If an answer is not provided, make a reasonable assumption and disclose it

## When Creating Code

For every connection parameter you provide, ensure you have enough context about
the user's application to justify the values. If not, ask targeted questions
first. If you get no answer, make a reasonable assumption, disclose it, and
comment the relevant parameters in the code.
