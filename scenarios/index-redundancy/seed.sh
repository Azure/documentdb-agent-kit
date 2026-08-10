#!/usr/bin/env bash
# seed.sh — load the "idx_test" fixture: a database with intentionally redundant
# and unused indexes, so index-redundancy-finder.sh has findings to report.
#
# Usage:
#   export DB_PASSWORD='<your-password>'
#   bash scenarios/index-redundancy/seed.sh            # -> database "idx_test"
#   bash scenarios/index-redundancy/seed.sh --db mydb --container NAME --password PASS
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER="${CONTAINER:-documentdb-local}"
PORT="${PORT:-10260}"
DB_USER="${DB_USER:-docdbadmin}"
PASSWORD="${DB_PASSWORD:-}"
DB="idx_test"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db)        DB="$2"; shift 2;;
        --container) CONTAINER="$2"; shift 2;;
        --password)  PASSWORD="$2"; shift 2;;
        --port)      PORT="$2"; shift 2;;
        -h|--help)   sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
        *)           echo "Unknown option: $1" >&2; exit 2;;
    esac
done

[[ -z "$PASSWORD" ]] && { echo "Error: no password. Set DB_PASSWORD or pass --password (e.g. export DB_PASSWORD='<your-password>')." >&2; exit 1; }

echo "Seeding redundant-index fixture into '${DB}' (container: ${CONTAINER}) ..."
docker cp "$DIR/fixture-redundant-indexes.js" "${CONTAINER}:/tmp/fixture-redundant-indexes.js" >/dev/null

docker exec "$CONTAINER" mongosh "localhost:${PORT}/${DB}" \
    -u "$DB_USER" -p "$PASSWORD" --authenticationMechanism SCRAM-SHA-256 \
    --tls --tlsAllowInvalidCertificates --quiet --file /tmp/fixture-redundant-indexes.js 2>/dev/null

echo
echo "Done. Try:  bash scripts/index-redundancy-finder.sh --db ${DB}"
