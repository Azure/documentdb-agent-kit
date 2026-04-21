---
name: documentdb-local-deployment
description: Best practices for running Azure DocumentDB locally for development — choosing between the Gateway Docker image and the psql-only image, docker-compose setup, connection config (port 10260, TLS, SCRAM-SHA-256), env-driven configuration, sample-data management (`SKIP_INIT_DATA` / `INIT_DATA_PATH`), port bindings, and dev/prod parity via versioned seed and schema scripts. Use when setting up a new local dev environment, writing sample apps, building integration tests, or diagnosing local connection problems.
license: MIT
---

# Local Deployment & Developer Workflow — Azure DocumentDB

Image choices:

- **Gateway** (`ghcr.io/microsoft/documentdb/documentdb-local:latest`) — MongoDB wire protocol on port **10260**. Use this for app development.
- **psql-only** (`mcr.microsoft.com/cosmosdb/ubuntu/documentdb-oss:...`) — raw PostgreSQL on port **9712**. Use only for direct SQL inspection.

## Rules

- [local-choose-deployment-method](local-choose-deployment-method.md) — Pick the simplest local option (Gateway, Compose, psql-only, or source) that matches the interface your app actually uses.
- [local-docker-compose-setup](local-docker-compose-setup.md) — Reproducible local stack via `docker-compose.yml`: pinned images, `host.docker.internal`, `restart: unless-stopped`.
- [local-connection-config](local-connection-config.md) — Connect on port 10260 with `--tls`, `--tlsAllowInvalidCertificates`, and SCRAM-SHA-256 for the self-signed local cert.
- [local-env-driven-config](local-env-driven-config.md) — Drive connection URI and TLS relaxation from env vars; never default `tlsAllowInvalidCertificates=true` in code.
- [local-sample-data-management](local-sample-data-management.md) — Use `SKIP_INIT_DATA` + `INIT_DATA_PATH` with vetted seed scripts; don't ship the built-in `sampledb` beyond local demos.
- [local-ports-and-bindings](local-ports-and-bindings.md) — Bind published ports to `127.0.0.1` and expose only what you use (10260 for Mongo, 9712 for psql).
- [local-prod-parity](local-prod-parity.md) — Same connection abstraction and versioned index/seed scripts across local and Azure DocumentDB; integration-test against the real container.
