# local-connection-config

**Category:** Local Deployment · **Priority:** HIGH

## Why it matters

The local DocumentDB Gateway ships with a **self-signed TLS certificate** and **SCRAM-SHA-256** authentication on port **10260**. Connections without `--tls` (or with the wrong auth mechanism) fail with confusing errors; disabling TLS verification in the wrong place silently creates insecure production defaults.

Minimum requirements for a working local connection:
- Port `10260`
- `--tls`
- `--tlsAllowInvalidCertificates` (for the self-signed local cert only)
- `--authenticationMechanism SCRAM-SHA-256`
- Username / password that match the container's env vars

## Incorrect

Non-TLS connection, or TLS without the cert-relaxation flag — both fail:

```bash
# Missing --tls — server rejects
mongosh localhost:10260 -u docdbuser -p 'Admin100!'

# --tls but without --tlsAllowInvalidCertificates — cert chain error
mongosh localhost:10260 -u docdbuser -p 'Admin100!' --tls
```

Hard-coding relaxed TLS inside library code (rather than at the call site) so it silently ends up in production:

```javascript
// ⚠️ buried default inside shared lib
function connect() {
  return new MongoClient(uri, { tls: true, tlsAllowInvalidCertificates: true });
}
```

## Correct

Use the documented flags at the connection point, not hidden in shared code.

`mongosh`:

```bash
mongosh localhost:10260 \
  -u docdbuser -p 'Admin100!' \
  --authenticationMechanism SCRAM-SHA-256 \
  --tls \
  --tlsAllowInvalidCertificates
```

Node MongoDB driver:

```javascript
import { MongoClient } from "mongodb";

const client = new MongoClient("mongodb://localhost:10260", {
  auth: { username: "docdbuser", password: "Admin100!" },
  tls: true,
  tlsAllowInvalidCertificates: true // local self-signed cert only
});
```

Python (PyMongo):

```python
from pymongo import MongoClient

client = MongoClient(
    "mongodb://localhost:10260",
    username="docdbuser",
    password="Admin100!",
    tls=True,
    tlsAllowInvalidCertificates=True  # local self-signed cert only
)
```

Always gate `tlsAllowInvalidCertificates` on an explicit environment flag (see `local-env-driven-config`) so it cannot be reused against a real deployment unchanged.

## References

- [DocumentDB docs site](https://documentdb.io/docs)
- [MongoDB connection options](https://www.mongodb.com/docs/manual/reference/connection-string/)
