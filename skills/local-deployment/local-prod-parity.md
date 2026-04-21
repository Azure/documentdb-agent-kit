# local-prod-parity

**Category:** Local Deployment · **Priority:** MEDIUM

## Why it matters

The local DocumentDB Gateway speaks the same MongoDB wire protocol as Azure DocumentDB, so with a little discipline **the same application code and the same index / seed scripts can run in both places**. Gaps in parity are where bugs hide: a query that works locally because of an implicit collation, or an index that exists only on a developer's machine.

Parity principles:
- **One connection abstraction** driven by environment variables (see `local-env-driven-config`). The only difference between local and cloud is the URI and the TLS flag.
- **Index definitions live in the repo**, not in a developer's mongosh history. Apply them identically to local and prod.
- **Seed vs. schema scripts are separate**: `seed/` data is local-only, `schema/` (indexes, collections) runs in every environment.
- **Test what prod does.** Integration tests target the local Gateway container, not an in-memory MongoDB — avoiding behaviour drift.
- **Version-pin the local image** so CI and dev laptops agree on engine behaviour.

## Incorrect

Developer creates an index in mongosh while debugging, and never moves it into the repo:

```javascript
// Typed at someone's terminal, then forgotten
db.orders.createIndex({ customerId: 1, createdAt: -1 });
// Works locally, missing in production -> 10x query latency on deploy
```

Or a sample project that runs against an in-memory MongoDB server locally but targets Azure DocumentDB in production — subtle operator differences surface only post-deploy.

## Correct

Check indexes and setup into source control, apply the same scripts to both environments.

`schema/01_indexes.js`:

```javascript
const db = db.getSiblingDB('app');

db.users.createIndex({ email: 1 }, { unique: true, name: 'users_email_unique' });
db.orders.createIndex({ customerId: 1, createdAt: -1 }, { name: 'orders_customer_recent' });
```

Apply to the local container via Compose-mounted `INIT_DATA_PATH`:

```yaml
services:
  documentdb:
    image: ghcr.io/microsoft/documentdb/documentdb-local:latest
    ports: ["127.0.0.1:10260:10260"]
    environment:
      - USERNAME=docdbuser
      - PASSWORD=${DOCUMENTDB_PASSWORD:?}
      - SKIP_INIT_DATA=true
      - INIT_DATA_PATH=/schema
    volumes:
      - ./schema:/schema:ro
```

And to Azure DocumentDB via a deployment script / CI step that runs the same `.js` files with `mongosh` against the cluster URI. Keep the file set, names, and ordering identical.

A minimal integration-test harness that brings the real container up:

```bash
docker compose up -d documentdb
./wait-for-port.sh 10260
npm run test:integration    # runs against mongodb://localhost:10260
docker compose down
```

Result: what works locally is what ships.

## References

- [Twelve-Factor App — Dev/prod parity](https://12factor.net/dev-prod-parity)
