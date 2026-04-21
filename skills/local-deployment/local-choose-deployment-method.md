# local-choose-deployment-method

**Category:** Local Deployment · **Priority:** HIGH

## Why it matters

DocumentDB can be run locally several ways: the prebuilt **Gateway image** (MongoDB wire protocol on port 10260), a **psql-only image** (direct PostgreSQL on port 9712), or a **source build**. Picking the wrong option for the use case wastes time — e.g. building from source for a demo, or running the psql-only image when your app talks the MongoDB wire protocol. Use the simplest option that gives the interface your application actually needs.

Decision matrix:

| Need | Recommended option |
|---|---|
| App talks MongoDB wire protocol (drivers / mongosh) | **Prebuilt Gateway image** (`ghcr.io/microsoft/documentdb/documentdb-local:latest`) |
| Sample project running app + DB together | **Docker Compose** on top of the Gateway image |
| Direct SQL / `documentdb_api.*` exploration only | Prebuilt **psql-only image** (`mcr.microsoft.com/cosmosdb/ubuntu/documentdb-oss:...`) |
| Hacking on the extensions / gateway code | **Build from source** (use the repo devcontainer) |

## Incorrect

Building DocumentDB from source for every sample repo, or teaching new contributors to run `sudo make install` + `build_and_install_with_pgrx.sh` when they just want to run a RAG demo:

```bash
# Overkill for an app developer
sudo make install
scripts/build_and_install_with_pgrx.sh -i -d pg_documentdb_gw_host/
scripts/start_oss_server.sh -c -g
```

## Correct

Start with the prebuilt Gateway image; drop down to source only when you must modify the engine.

```bash
docker run -dt \
  -p 10260:10260 \
  -e USERNAME=docdbuser \
  -e PASSWORD='Admin100!' \
  ghcr.io/microsoft/documentdb/documentdb-local:latest
```

Then connect with any MongoDB client (`mongosh`, Node driver, PyMongo) on `localhost:10260`.

## References

- [DocumentDB GitHub](https://github.com/microsoft/documentdb)
- [DocumentDB docs site](https://documentdb.io/docs)
