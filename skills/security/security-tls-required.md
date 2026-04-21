# security-tls-required

**Category:** Security · **Priority:** HIGH

## Why it matters

Azure DocumentDB requires TLS on all connections. Disabling certificate validation to "make the connection work" exposes traffic to man-in-the-middle attacks and leaks credentials. Most `MongoServerSelectionError` / `self signed certificate` issues are either missing CA bundles or misconfigured SNI — not a reason to disable TLS.

## Incorrect

```javascript
// Disabling TLS verification to paper over a cert chain issue
const client = new MongoClient(uri, {
  tls: true,
  tlsAllowInvalidCertificates: true,   // 🚨
  tlsAllowInvalidHostnames: true       // 🚨
});
```

## Correct

```javascript
// Rely on the system CA store; ensure your runtime's CAs are up to date.
const client = new MongoClient(uri, {
  tls: true,
  retryWrites: true
});
```

If you run in a restricted environment (container with no CA bundle), install `ca-certificates` (or equivalent) and/or point the driver at a specific CA file rather than disabling verification.

## References

- [Security in Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/security)
