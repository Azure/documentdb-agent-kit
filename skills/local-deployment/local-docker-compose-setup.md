# local-docker-compose-setup

**Category:** Local Deployment · **Priority:** HIGH

## Why it matters

Running DocumentDB and the app under a single `docker compose up` makes local setup reproducible across machines, gives a clean teardown (`docker compose down`), and ensures every developer hits the same database version. Ad-hoc `docker run` chains drift quickly and make onboarding painful.

Key things to get right in Compose:
- Pin the image (or at minimum use `:latest` consciously, knowing it will drift).
- Expose port **10260** (Gateway/Mongo wire protocol). Only expose **9712** (psql) if the app actually needs raw SQL.
- Use `restart: unless-stopped` so the DB survives reboots but still honours explicit `down`.
- Add `extra_hosts: ["host.docker.internal:host-gateway"]` on the app service so containers on Linux can reach the host consistently.
- `depends_on` does **not** wait for DocumentDB to be *ready*, only started — add a driver-level retry or a wait-for-port helper.

## Incorrect

Ad-hoc startup with unpinned flags scattered across a README:

```bash
# Different in every developer's terminal history
docker run -p 10260:10260 -e USERNAME=u -e PASSWORD=p ghcr.io/microsoft/documentdb/documentdb-local:latest
npm start
# …where's the password? which image version? how do I stop it?
```

## Correct

Commit a `docker-compose.yml` to the repo:

```yaml
services:
  documentdb:
    image: ghcr.io/microsoft/documentdb/documentdb-local:latest
    ports:
      - "10260:10260"
    environment:
      - USERNAME=docdbuser
      - PASSWORD=${DOCUMENTDB_PASSWORD:?DOCUMENTDB_PASSWORD is required}
    restart: unless-stopped

  app:
    build: .
    ports:
      - "3000:3000"
    env_file:
      - .env
    depends_on:
      - documentdb
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped
```

Start / stop:

```bash
docker compose up -d
docker compose logs -f documentdb
docker compose down
```

Connection strings:
- From the **host machine** → `localhost:10260`
- From **another container** in the same compose network → `documentdb:10260` (service name) or `host.docker.internal:10260`

For DB-only samples, omit the `app` service and include only `documentdb`.

## References

- [Docker Compose reference](https://docs.docker.com/compose/)
- [DocumentDB local image on GHCR](https://github.com/microsoft/documentdb)
