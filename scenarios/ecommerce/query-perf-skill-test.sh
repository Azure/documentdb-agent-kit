#!/usr/bin/env bash
# query-perf-skill-test.sh — run the query-performance skill before/after harness
# against the seeded `ecommerce` dataset in a local DocumentDB container.
#
# Prereq: a running `documentdb-local` container with the ecommerce dataset seeded
#   export DB_PASSWORD='<your-password>'
#   bash scenarios/ecommerce/seed.sh
#   bash scenarios/ecommerce/query-perf-skill-test.sh
#
# Read-only against your data except that it CREATES then DROPS its own test
# indexes on `orders` (leaving the collection with only its default _id index).
set -uo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-documentdb-local}"
PORT="${PORT:-10260}"
USER="${DB_USER:-docdbadmin}"
PASSWORD="${DB_PASSWORD:-}"
DB="ecommerce"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JS="$HERE/query-perf-skill-test.js"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --container) CONTAINER_NAME="$2"; shift 2;;
        --password)  PASSWORD="$2"; shift 2;;
        --port)      PORT="$2"; shift 2;;
        --db)        DB="$2"; shift 2;;
        -h|--help)   echo "Usage: $0 [--container NAME] [--password PASS] [--port PORT] [--db NAME]"; exit 0;;
        *)           shift;;
    esac
done

[[ -z "$PASSWORD" ]] && { echo "Error: no password. Set DB_PASSWORD or pass --password (e.g. export DB_PASSWORD='<your-password>')." >&2; exit 1; }
[[ -f "$JS" ]] || { echo "Error: harness not found at $JS" >&2; exit 1; }

# Copy the harness into the container and run it with the bundled mongosh.
docker cp "$JS" "${CONTAINER_NAME}:/tmp/query-perf-skill-test.js" >/dev/null
docker exec -u documentdb "$CONTAINER_NAME" mongosh \
    "localhost:${PORT}/${DB}" -u "$USER" -p "$PASSWORD" \
    --authenticationMechanism SCRAM-SHA-256 --tls --tlsAllowInvalidCertificates \
    --quiet --file /tmp/query-perf-skill-test.js
