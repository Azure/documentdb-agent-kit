# index-ttl-expiry

**Category:** Indexing · **Priority:** MEDIUM

## Why it matters

A **TTL (Time-To-Live)** index auto-deletes documents N seconds after a date in the indexed field. Perfect for sessions, caches, feature-flag overrides, short-lived audit logs — anything that self-expires. Done correctly, it removes the need for a reaper cron job.

Key semantics that trip people up:

- The indexed field **must be a `Date`** (not a number, not a string). Non-Date values are silently skipped.
- A background thread deletes expired documents roughly every 60 seconds — expiry is not second-accurate.
- TTL works on a **single-field, non-compound, non-multikey** index. `{ createdAt: 1 }` with `expireAfterSeconds` is fine; `{ createdAt: 1, userId: 1 }` is not a TTL index.
- Setting `expireAfterSeconds: 0` combined with an explicit `expiresAt` date field gives you "delete at a specific time" semantics.

## Incorrect

Indexing a field that isn't a Date:

```javascript
db.sessions.insertOne({ sessionId: "s1", createdAt: Date.now() });  // number, not Date
db.sessions.createIndex({ createdAt: 1 }, { expireAfterSeconds: 3600 });
// Index exists but nothing ever expires.
```

Putting the TTL on a compound index:

```javascript
db.sessions.createIndex(
  { userId: 1, createdAt: 1 },
  { expireAfterSeconds: 3600 }
);
// Not a valid TTL index. Expiration will not run.
```

Assuming expiry is instant:

```javascript
// Sets a session to "expire in 2 seconds"
db.sessions.insertOne({ expiresAt: new Date(Date.now() + 2000) });
db.sessions.createIndex({ expiresAt: 1 }, { expireAfterSeconds: 0 });
// Actual deletion may lag up to ~60 seconds — don't rely on TTL for tight deadlines.
```

## Correct

Relative expiry — "N seconds after `createdAt`":

```javascript
db.sessions.insertOne({
  sessionId: "s1",
  userId: ObjectId(),
  createdAt: new Date()                     // a real Date
});

db.sessions.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 24 * 60 * 60 }      // 24 hours
);
```

Absolute expiry — "delete at this specific time":

```javascript
db.sessions.insertOne({
  sessionId: "s1",
  expiresAt: new Date(Date.now() + 60 * 60 * 1000)   // 1 hour from now
});

db.sessions.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }                 // expire exactly when expiresAt is reached
);
```

Monitoring — make sure the TTL monitor is actually running:

```javascript
// How many docs are past due?
db.sessions.countDocuments({ expiresAt: { $lt: new Date() } });
// Consistently non-zero and growing => TTL background job isn't keeping up.
```

Guidelines:

- Only one TTL field per collection — if you need multiple expirations, split into separate collections.
- Don't rely on TTL for security-critical deletion windows; the background sweeper may lag under heavy load.
- Document the TTL intent with a descriptive index name (`{ name: "sessions_ttl_24h" }`).

## References

- [MongoDB TTL indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
