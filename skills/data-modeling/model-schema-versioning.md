# model-schema-versioning

**Category:** Data Modeling · **Priority:** MEDIUM

## Why it matters

Document schemas evolve. Without a version marker, application code must handle every historical shape implicitly via `if` chains, and migrations become risky all-or-nothing operations. A `schemaVersion` field enables **lazy per-document migration** and safe forward evolution.

## Incorrect

```javascript
// No version; code silently handles both shapes
if (Array.isArray(doc.addresses)) { /* new */ } else { /* old */ }
```

## Correct

```javascript
{
  _id: ...,
  schemaVersion: 2,
  addresses: [ { line1, city, country } ]
}

// On read, migrate if needed and write back
function normalize(doc) {
  if (doc.schemaVersion === 1) {
    doc.addresses = [doc.address];
    delete doc.address;
    doc.schemaVersion = 2;
    users.updateOne({ _id: doc._id, schemaVersion: 1 }, { $set: doc });
  }
  return doc;
}
```

## References

- MongoDB Schema Versioning pattern
