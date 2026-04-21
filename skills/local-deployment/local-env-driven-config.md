# local-env-driven-config

**Category:** Local Deployment · **Priority:** HIGH

## Why it matters

Samples and dev setups routinely leak two problems into production:
1. Hard-coded passwords checked into source.
2. `tlsAllowInvalidCertificates: true` defaults that silently disable cert validation when the same code is pointed at a managed Azure DocumentDB cluster.

A small discipline fixes both: **read the connection URI from an env var, require it to be set, and drive any dangerous TLS relaxation from a separate explicit flag that defaults to `false`.** The local container turns the flag on *explicitly*; production clusters leave it unset and cert validation works normally.

## Incorrect

Hard-coded local URI with TLS relaxation baked in:

```python
client = MongoClient(
    "mongodb://docdbuser:Admin100!@localhost:10260/?tls=true",
    tlsAllowInvalidCertificates=True  # ⚠️ defaults to insecure for every environment
)
```

Or an env var with an insecure default:

```python
client = MongoClient(
    os.getenv("DOCUMENTDB_URI", "mongodb://docdbuser:Admin100!@localhost:10260/?tls=true&tlsAllowInvalidCertificates=true"),
    tlsAllowInvalidCertificates=True
)
```

Production runs of the same image with no env vars still get the insecure default.

## Correct

```python
import os
import sys
from pymongo import MongoClient


def get_client() -> MongoClient:
    uri = os.getenv("DOCUMENTDB_URI")
    if not uri:
        sys.exit(
            "Error: DOCUMENTDB_URI environment variable is not set.\n"
            "Copy .env.example to .env and fill in your connection string."
        )
    # Only safe for the local dev container — never enable against a real deployment.
    allow_invalid_certs = (
        os.getenv("DOCUMENTDB_ALLOW_INVALID_CERTS", "false").lower() == "true"
    )
    return MongoClient(uri, tlsAllowInvalidCertificates=allow_invalid_certs)
```

`.env.example` committed to the repo (secrets themselves go in an uncommitted `.env`):

```dotenv
# Local container — self-signed cert, opt into insecure TLS explicitly
DOCUMENTDB_URI=mongodb://<username>:<password>@localhost:10260/?tls=true&tlsAllowInvalidCertificates=true&authMechanism=SCRAM-SHA-256
DOCUMENTDB_ALLOW_INVALID_CERTS=true
```

For a real Azure DocumentDB cluster, the production `.env` simply:

```dotenv
DOCUMENTDB_URI=mongodb+srv://<user>:<pw>@<cluster>.mongocluster.documentdb.azure.com/?tls=true&authMechanism=SCRAM-SHA-256
# DOCUMENTDB_ALLOW_INVALID_CERTS is unset -> defaults to false, cert validation enforced
```

Rules:
- Never ship a default URI in code.
- Never default `tlsAllowInvalidCertificates` to `true`.
- Keep `.env` out of source control (`.gitignore`); commit `.env.example`.
- Reflect the same pattern in Node (`process.env.DOCUMENTDB_URI`) and C# (`Environment.GetEnvironmentVariable`).

## References

- [Twelve-Factor App — Config](https://12factor.net/config)
