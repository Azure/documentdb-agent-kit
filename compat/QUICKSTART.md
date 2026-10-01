# Azure DocumentDB e-commerce quick-start

This is a MongoDB-compatible Node.js project running **entirely on Azure
DocumentDB**. It uses the official `mongodb` driver and standard query syntax;
no MongoDB server is required.

> Azure DocumentDB and this agent kit are in public preview. This is a local
> compatibility demonstration, not production deployment guidance.

The minimal project-generation prompt is in [`PROMPT.md`](PROMPT.md).

## What is tested

The deterministic seed creates:

| Collection | Documents |
|---|---:|
| `customers` | 12 |
| `products` | 16 |
| `orders` | 48 |
| `order_items` | 96 |
| `inventory` | 32 |

The four exact-result checks cover:

1. A filtered and sorted `find()`.
2. Orders grouped by customer, then joined to `customers` with `$lookup`.
3. One order joined to its customer and `order_items`.
4. Products joined to `inventory`.

The workload uses `$match`, `$group`, `$lookup`, `$unwind`, `$project`,
`$sort`, `$limit`, `$size`, and `$sum`.

## 1. Install

```bash
cd compat
npm ci
```

The source creates one process-wide `MongoClient`. Authentication and TLS are
configured entirely through `MONGODB_URI`.

## 2. Start DocumentDB Local

```bash
export DOCDB_PASSWORD='<choose-a-password>'

docker rm -f documentdb-compat 2>/dev/null || true
docker run -d --name documentdb-compat \
  -p 127.0.0.1:10261:10260 \
  ghcr.io/microsoft/documentdb/documentdb-local:latest \
  --username docdbadmin \
  --password "$DOCDB_PASSWORD"
```

Wait for the gateway port:

```bash
until (echo >/dev/tcp/127.0.0.1/10261) 2>/dev/null; do sleep 1; done
```

## 3. Run the end-to-end workflow

```bash
ENCODED_PASSWORD=$(node -p 'encodeURIComponent(process.argv[1])' "$DOCDB_PASSWORD")
export MONGODB_URI="mongodb://docdbadmin:${ENCODED_PASSWORD}@127.0.0.1:10261/?tls=true&tlsAllowInvalidCertificates=true"

npm test

RESULT_FILE=results/documentdb.json npm run query >/dev/null
sha256sum results/documentdb.json
```

For Azure-hosted DocumentDB, replace `MONGODB_URI` with the Azure connection
string and do not enable `tlsAllowInvalidCertificates`.

## Result

```text
{"database":"ecommerce_compat","counts":{"customers":12,"products":16,"orders":48,"order_items":96,"inventory":32}}
{"status":"PASS","checks":4,"query_shapes":{"find":1,"lookup_aggregations":3}}
ELAPSED_SECONDS=12.22
```

The elapsed time is one local functional run started as soon as the gateway
port opened; it includes the remaining driver wait for full readiness. It is
recorded for reproducibility, not as a performance benchmark.

## What this demonstrates

| Surface | Result |
|---|---|
| Official Node.js `mongodb` driver | PASS |
| Deterministic seed and index creation | PASS |
| Filter + projection + sort | PASS |
| `$group` + customer `$lookup` | PASS |
| Order + customer + item `$lookup` | PASS |
| Product + inventory `$lookup` | PASS |
| Exact expected output | PASS |

This demonstrates the tested MongoDB-compatible surface only; it does not imply
that every MongoDB feature is supported. Check advanced operators against the
[DocumentDB compatibility documentation](https://learn.microsoft.com/azure/documentdb/compatibility).
