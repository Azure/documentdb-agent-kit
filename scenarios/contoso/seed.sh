#!/usr/bin/env bash
# seed.sh — load ONE base-size Contoso (Dynamics-365-Sales) demo database.
#
# Seeds the entities territories/users/products/campaigns/accounts/opportunities
# with the DocumentDB TOAST anti-pattern deliberately planted: large, varied text
# (narrative + activity_log ~6 KB) is co-located on `opportunities`, so it lands
# in PostgreSQL TOAST and gets detoasted on every scan. This is the dataset the
# `toast-split-advisor` skill / `document-bloat-advisor.sh` diagnose.
#
# This is the QUICKSTART seeder: a single, base-size database (no scaling). For
# the optional scaling benchmark see scaling-benchmark/.
#
# Usage:
#   bash scenarios/contoso/seed.sh                       # -> database "contoso"
#   bash scenarios/contoso/seed.sh --db mycontoso
#   bash scenarios/contoso/seed.sh --container NAME --password PASS
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER="${CONTAINER:-documentdb-local}"
PORT="${PORT:-10260}"
DB_USER="${DB_USER:-docdbadmin}"
PASSWORD="${DB_PASSWORD:-}"
DB="contoso"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db)        DB="$2"; shift 2;;
        --container) CONTAINER="$2"; shift 2;;
        --password)  PASSWORD="$2"; shift 2;;
        --port)      PORT="$2"; shift 2;;
        -h|--help)   sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
        *)           echo "Unknown option: $1" >&2; exit 2;;
    esac
done

[[ -z "$PASSWORD" ]] && { echo "Error: no password. Set DB_PASSWORD or pass --password (e.g. export DB_PASSWORD='<your-password>')." >&2; exit 1; }

echo "Seeding base-size Contoso into '${DB}' (container: ${CONTAINER}) ..."
docker cp "$DIR/contoso-seed.js" "${CONTAINER}:/tmp/contoso-seed.js" >/dev/null

docker exec -e CONTOSO_DB="$DB" -e CONTOSO_SCALE=1 "$CONTAINER" mongosh \
    "localhost:${PORT}/${DB}" -u "$DB_USER" -p "$PASSWORD" \
    --authenticationMechanism SCRAM-SHA-256 --tls --tlsAllowInvalidCertificates \
    --quiet --file /tmp/contoso-seed.js 2>/dev/null

echo
echo "Done. Try:"
echo "  bash scripts/document-bloat-advisor.sh --db ${DB}"
echo "  bash scripts/toast-split-advisor.sh --db ${DB}"
