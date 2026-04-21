# local-ports-and-bindings

**Category:** Local Deployment · **Priority:** MEDIUM

## Why it matters

DocumentDB exposes two distinct endpoints on different ports — publishing the wrong one, or publishing them on all interfaces instead of loopback, causes either "nothing connects" or "my laptop's DB is on the coffee-shop Wi-Fi".

| Port | Protocol | Who connects | Typical use |
|---|---|---|---|
| **10260** | MongoDB wire protocol (via Gateway) | MongoDB drivers, `mongosh` | App development, integration tests |
| **9712** | PostgreSQL wire protocol | `psql`, SQL clients, `documentdb_api.*` | Deep inspection, raw SQL tuning |

Rules:
- Publish only the ports your workflow actually uses. Most apps only need **10260**.
- When exposing a port from a container on a developer laptop, bind to **`127.0.0.1`** (loopback), not `0.0.0.0`. Otherwise every network the laptop joins can reach the DB.
- In CI, bind to loopback too; agents share network namespaces with other jobs.

## Incorrect

Publishing on all interfaces and opening both ports "just in case":

```bash
docker run -dt \
  -p 0.0.0.0:10260:10260 \
  -p 0.0.0.0:9712:9712 \
  -e USERNAME=docdbuser -e PASSWORD='Admin100!' \
  ghcr.io/microsoft/documentdb/documentdb-local:latest
```

Now any peer on the local network can attempt SCRAM auth against the local instance.

## Correct

Loopback-only, minimal ports:

```bash
# App development — Gateway only, loopback only
docker run -dt \
  -p 127.0.0.1:10260:10260 \
  -e USERNAME=docdbuser -e PASSWORD='Admin100!' \
  ghcr.io/microsoft/documentdb/documentdb-local:latest
```

```bash
# SQL inspection session — psql-only image, loopback only
docker run -p 127.0.0.1:9712:9712 -dt \
  mcr.microsoft.com/cosmosdb/ubuntu/documentdb-oss:22.04-PG16-AMD64-0.103.0 -e

psql -h localhost --port 9712 -d postgres -U documentdb
```

Docker Compose equivalent:

```yaml
services:
  documentdb:
    image: ghcr.io/microsoft/documentdb/documentdb-local:latest
    ports:
      - "127.0.0.1:10260:10260"
```

If a teammate legitimately needs to reach your local DB, prefer an SSH tunnel (`ssh -L 10260:localhost:10260 you@host`) over binding to `0.0.0.0`.

## References

- [Docker port publishing](https://docs.docker.com/engine/network/#published-ports)
