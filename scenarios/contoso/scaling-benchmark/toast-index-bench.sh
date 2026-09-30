#!/usr/bin/env bash
# toast-index-bench.sh — sweep a matrix of index configurations against the
# canonical Contoso BI queries and record the detoast tax (PG block traffic +
# docs examined + timing). Run it once BEFORE the schema split and once AFTER to
# get an apples-to-apples before/after table at identical row counts.
#
# Emits a TSV to stdout (one row per index-config x query) plus per-config
# heap/TOAST bytes. Meant to be captured into a report log.
#
# Usage:
#   bash toast-index-bench.sh --db contoso_x16 --phase before
#   bash toast-index-bench.sh --db contoso_x16 --phase after
set -uo pipefail

CONTAINER="${CONTAINER:-documentdb-local}"
PORT="${PORT:-10260}"
PG_PORT="${PG_PORT:-9712}"
PG_USER="${PG_USER:-documentdb}"
DB_USER="${DB_USER:-docdbadmin}"
PASSWORD="${DB_PASSWORD:-}"
DB="contoso_x16"
PHASE="before"
REPS="${QUERY_REPS:-7}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db) DB="$2"; shift 2;;
        --phase) PHASE="$2"; shift 2;;
        --reps) REPS="$2"; shift 2;;
        *) echo "unknown arg $1" >&2; exit 2;;
    esac
done

[[ -z "$PASSWORD" ]] && { echo "Error: no password. Set DB_PASSWORD or pass --password (e.g. export DB_PASSWORD='<your-password>')." >&2; exit 1; }

mongo() {
    docker exec "$CONTAINER" mongosh "localhost:${PORT}/${DB}" \
        -u "$DB_USER" -p "$PASSWORD" --authenticationMechanism SCRAM-SHA-256 \
        --tls --tlsAllowInvalidCertificates --quiet --eval "$1" 2>/dev/null
}
psql_q() {
    docker exec "$CONTAINER" psql -h localhost -p "$PG_PORT" -U "$PG_USER" -d postgres \
        -t --no-align -F $'\t' -c "$1" 2>/dev/null | grep -vE '^(SET)?$'
}

# copy the probe into the container once
docker cp "$(dirname "$0")/toast-index-probe.js" "${CONTAINER}:/tmp/toast-index-probe.js" >/dev/null 2>&1

run_probe() { # $1=query $2=label
    docker exec -e CONTOSO_DB="$DB" -e QUERY="$1" -e IDX_LABEL="$2" -e QUERY_REPS="$REPS" \
        "$CONTAINER" mongosh "localhost:${PORT}/${DB}" \
        -u "$DB_USER" -p "$PASSWORD" --authenticationMechanism SCRAM-SHA-256 \
        --tls --tlsAllowInvalidCertificates --quiet --file /tmp/toast-index-probe.js 2>/dev/null \
        | grep '^IDXRESULT' | sed 's/^IDXRESULT //'
}

# drop every secondary index (keep _id_) so each config starts clean
reset_indexes() {
    mongo '
        db.opportunities.getIndexes().forEach(function(i){
            if (i.name !== "_id_") { try { db.opportunities.dropIndex(i.name); } catch(e){} }
        });
    ' >/dev/null
}

heap_toast() { # -> "heap_bytes<TAB>toast_bytes"
    psql_q "
    SELECT pg_relation_size(t.oid),
           COALESCE(pg_relation_size(NULLIF(t.reltoastrelid,0)),0)
    FROM documentdb_api_catalog.collections c
    JOIN pg_class t ON t.oid = ('documentdb_data.documents_'||c.collection_id)::regclass
    WHERE c.database_name='${DB}' AND c.collection_name='opportunities';"
}

# ── index configurations to sweep ──────────────────────────────────────────
# label|createIndex spec ("" = none, baseline _id_ only)
CONFIGS=(
    "baseline_id_only|"
    "single_state|{state:1}"
    "compound_state_terr|{state:1,territory_id:1}"
    "covering_attempt|{state:1,territory_id:1,est_value:1}"
    "group_key_only|{territory_id:1}"
)

read -r HEAP TOAST <<<"$(heap_toast)"
echo "# phase=${PHASE} db=${DB} opps heap_bytes=${HEAP} toast_bytes=${TOAST} reps=${REPS}"
printf 'phase\tquery\tconfig\tindex_used\tstage\tdocs_examined\tblocks_total\tblocks_mib\tplan_ms\tmin_ms\trows\n'

for QUERY in selective fullscan; do
    for entry in "${CONFIGS[@]}"; do
        label="${entry%%|*}"
        spec="${entry#*|}"
        reset_indexes
        if [[ -n "$spec" ]]; then
            mongo "db.opportunities.createIndex(${spec});" >/dev/null
        fi
        json="$(run_probe "$QUERY" "$label")"
        [[ -z "$json" ]] && { echo -e "${PHASE}\t${QUERY}\t${label}\tERROR"; continue; }
        # extract fields with python (stdlib) for robustness
        echo "$json" | python3 -c '
import sys, json
d = json.load(sys.stdin)
print("\t".join(str(x) for x in [
    "'"$PHASE"'", d["query"], d["idx"], d["index_used"], d["stage"],
    d["docs_examined"], d["blocks_total"], d["blocks_mib"],
    d["plan_ms"], d["min_ms"], d["rows"]
]))'
    done
done

reset_indexes
