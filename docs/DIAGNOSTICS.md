# Diagnostic Toolbox — end-to-end guide

The kit ships **deterministic diagnostic scripts** plus a **knowledge-base router**
for a *local* DocumentDB container. They complement the text skills: where a skill
tells an agent *what to consider*, these tools **measure the live database** and
return an evidence-based answer — reading both the MongoDB API (`mongosh`) and the
PostgreSQL engine underneath (`psql`).

Everything here runs against a Docker container and needs only `docker`, `bash`,
and `python3` on the host — no MCP server, no cloud, no API keys.

| Piece | Path | What it is |
|-------|------|-----------|
| Diagnostic scripts | [`scripts/`](../scripts/) | 5 read-only analyzers (TOAST/bloat, index redundancy, config/cache, perf, data integrity). |
| Knowledge-base router | [`knowledge-base/`](../knowledge-base/README.md) | Deterministic NL question → exact script (no LLM at routing time). |
| Demo datasets | [`scenarios/ecommerce/`](../scenarios/ecommerce/), [`scenarios/contoso/`](../scenarios/contoso/README.md) | Seeders that plant the problems the tools find. |
| Regression tests | [`testing/`](../testing/README.md) | Fixture-first contracts that guard the scripts. |
| Token study | [`token-tests/`](../token-tests/README.md) | Measured token savings of scripts vs text-skill workflows. |

---

## 0. Start a local DocumentDB container

Use the open-source Gateway image. Name it `documentdb-local` and pick a
password; the scripts read it from `DB_USER` (default `docdbadmin`) and
`DB_PASSWORD` — **nothing is baked in**:

```bash
# the scripts require a password — export it once (or pass --password each time)
export DB_PASSWORD='<choose-a-password>'

docker run -dt --name documentdb-local \
  -p 10260:10260 \
  -e USERNAME=docdbadmin \
  -e PASSWORD="$DB_PASSWORD" \
  ghcr.io/microsoft/documentdb/documentdb-local:latest

# preflight: confirm the engine answers (should print "1")
docker exec documentdb-local psql -h localhost -p 9712 -U documentdb -d postgres -tAc "SELECT 1"
```

The scripts `docker exec` into this container (MongoDB API on 10260, PostgreSQL on
9712 internally), so **publishing ports is optional**. If you use different
credentials or a different container name, pass `--container` / `--password` or set
`DB_USER` / `DB_PASSWORD` / `PORT` / `PG_PORT` env vars — every script honors them.

## 1. Seed demo data

```bash
bash scenarios/ecommerce/seed.sh           # -> database "ecommerce"
bash scenarios/contoso/seed.sh             # -> database "contoso"  (TOAST demo)
```

## 2. Run the diagnostics

```bash
# Large-document / TOAST detoast tax (analysis only — no data changes)
bash scripts/document-bloat-advisor.sh   --db contoso

# Redundant / unused indexes you can drop
bash scripts/index-redundancy-finder.sh  --db ecommerce

# Working set vs cache, TOAST share, cache-hit ratios
bash scripts/db-config-advisor.sh        --db contoso

# Overall health: collection-scan audit, query timing, PG I/O / locks / config
bash scripts/perf-advisor.sh             --db ecommerce

# Orphaned foreign keys + mixed field types (hard structural integrity)
bash scripts/data-integrity-check.sh     --db ecommerce
```

Add `--json` to any of them for a compact machine-readable result (what the router
and agents consume):

```bash
bash scripts/document-bloat-advisor.sh --db contoso --json
```

## 3. Natural-language routing (optional)

Don't know which tool you need? Ask in plain language — the router maps it to the
exact script, deterministically, **without a container or an LLM**:

```bash
bash knowledge-base/kb-route.sh --db contoso "why are my aggregations slow even though I have indexes"
#   → document-bloat-advisor  ·  run: bash scripts/document-bloat-advisor.sh --db contoso [--json]

# see the scoring walkthrough
python3 knowledge-base/kb_route_demo.py "which indexes can I drop"
```

## 4. See the TOAST fix in action (optional)

```bash
# apply the schema split the advisor recommends, then re-run the advisor
docker cp scenarios/contoso/contoso-split-fix.js documentdb-local:/tmp/fix.js
docker exec -e CONTOSO_DB=contoso documentdb-local mongosh \
  "localhost:10260/contoso" -u docdbadmin -p "$DB_PASSWORD" \
  --authenticationMechanism SCRAM-SHA-256 --tls --tlsAllowInvalidCertificates \
  --quiet --file /tmp/fix.js
bash scripts/document-bloat-advisor.sh --db contoso     # opportunities now clean
```

## 5. Run the regression tests (optional)

```bash
bash testing/run.sh          # fixture-first contracts; auto-creates a venv
```

## 6. Reproduce the token study (optional)

```bash
cd token-tests
bash token-ab-measure.sh | python3 summarize.py     # see RESULTS.md for the table
```

---

## Connection defaults

| Setting | Default | Override |
|---|---|---|
| container | `documentdb-local` | `--container` |
| Mongo port | `10260` | `--port` / `PORT` |
| PG port | `9712` | `--pg-port` / `PG_PORT` |
| Mongo user | `docdbadmin` | `DB_USER` |
| password | *(required)* | `--password` / `DB_PASSWORD` |
| PG user | `documentdb` | `PG_USER` |

## Notes

- The scripts are **read-only** — they never modify data. The only script that
  changes data is the explicit, opt-in `contoso-split-fix.js` demo in step 4.
- The scaling benchmark under
  [`scenarios/contoso/scaling-benchmark/`](../scenarios/contoso/scaling-benchmark/README.md)
  is **optional/advanced** (multi-scale x1…x16) and is **not** part of this quickstart.
