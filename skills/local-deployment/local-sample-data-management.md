# local-sample-data-management

**Category:** Local Deployment · **Priority:** MEDIUM

## Why it matters

The DocumentDB local image seeds a `sampledb` database on first start (`users`, `products`, `orders`, `analytics`) — convenient for a first-run demo, actively harmful in any shared / staging / production context. Ambient sample data hides real data, confuses automated tests, and leaks into dashboards. Teams should treat the built-in seed as **local-first-run only** and drive all non-trivial seeding from version-controlled scripts.

Env-var contract (image):

| Variable | Default | Use |
|---|---|---|
| `SKIP_INIT_DATA` | `false` | Set `true` to skip the built-in sample dataset |
| `INIT_DATA_PATH` | `/init_doc_db.d` | Directory of `.js` scripts executed in alphabetical order via `mongosh` |

## Incorrect

Shipping images to shared environments without disabling the seed:

```yaml
services:
  documentdb:
    image: ghcr.io/microsoft/documentdb/documentdb-local:latest
    ports: ["10260:10260"]
    environment:
      - USERNAME=docdbuser
      - PASSWORD=${DOCUMENTDB_PASSWORD:?}
      # SKIP_INIT_DATA not set -> sampledb is created in every env
```

Or mounting ad-hoc seed SQL scripts rather than MongoDB-shell (`.js`) scripts — the image's init pipeline runs `.js` through `mongosh`, not SQL.

## Correct

Explicitly opt in to the sample dataset for first-run demos, opt out everywhere else, and provide your own vetted seeds via `INIT_DATA_PATH`.

```yaml
services:
  documentdb:
    image: ghcr.io/microsoft/documentdb/documentdb-local:latest
    ports: ["10260:10260"]
    environment:
      - USERNAME=docdbuser
      - PASSWORD=${DOCUMENTDB_PASSWORD:?}
      - SKIP_INIT_DATA=${SKIP_INIT_DATA:-true}
      - INIT_DATA_PATH=/seed
    volumes:
      - ./seed:/seed:ro
```

Example `seed/00_indexes.js` (runs first because of the `00_` prefix):

```javascript
db.getSiblingDB('app').createCollection('users');
db.getSiblingDB('app').users.createIndex({ email: 1 }, { unique: true });
```

Example `seed/10_data.js`:

```javascript
db.getSiblingDB('app').users.insertMany([
  { _id: 1, email: 'ada@example.com', name: 'Ada' },
  { _id: 2, email: 'linus@example.com', name: 'Linus' }
]);
```

Guidelines:
- Keep `seed/` in version control; treat it like schema migrations.
- Name files with numeric prefixes to control execution order.
- Idempotent scripts only — they may re-run if the container volume is recreated.
- In production, always set `SKIP_INIT_DATA=true` and mount only vetted scripts.

## References

- DocumentDB local image README (GHCR)
