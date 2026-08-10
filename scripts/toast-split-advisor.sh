#!/usr/bin/env bash
# toast-split-advisor.sh — DocumentDB large-document / TOAST *analysis* tool.
#
# ANALYSIS ONLY. This script REPORTS where a collection would benefit from
# splitting a large field into a side collection. It NEVER moves data, drops a
# field, or runs VACUUM — applying a split is an operator decision (and, at
# scale, must be done in throttled batches; see the guidance this tool prints).
#
# Why this exists (DocumentDB-specific):
#   Each document is a single BSON column in PostgreSQL. A large, low-
#   compressibility field (long text, blobs) pushes the value out-of-line into a
#   TOAST table. Because the whole document is ONE column, reading ANY scalar
#   field detoasts the ENTIRE document — so co-locating big text with fields your
#   queries scan/aggregate imposes a per-access "detoast tax" that never shows up
#   as a missing index. Projection does NOT help (the row is detoasted server-
#   side before projection). The fix is schema separation: move the large field
#   into a side collection keyed by _id, so the hot collection stays small/inline.
#
# What it measures (no guessing):
#   - per-collection heap vs TOAST bytes (PostgreSQL, cross-layer)  -> is there a tax?
#   - MongoDB avgObjSize + per-top-level-field average size (sampled) -> WHICH field
#   - projected hot-document size AFTER removing the split candidates -> will it
#     drop below PostgreSQL's ~2 KB TOAST threshold and stay inline?
#
# Usage:
#   bash scripts/toast-split-advisor.sh --db <name> [--collection <name>] [--json]
#     [--container NAME] [--port 10260] [--pg-port 9712]
#     [--toast-ratio 0.5]      flag when TOAST/(heap+TOAST) exceeds this
#     [--min-total-kb 256]     ignore collections smaller than this
#     [--field-min-bytes 1024] a field must average >= this to be a split candidate
#     [--sample 100]           documents sampled per collection for field sizing
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CONTAINER_NAME="${CONTAINER_NAME:-documentdb-local}"
PORT="${PORT:-10260}"
PG_PORT="${PG_PORT:-9712}"
PG_USER="${PG_USER:-documentdb}"
PG_DB="${PG_DB:-postgres}"
DB_USER_="${DB_USER:-docdbadmin}"
PASSWORD="${DB_PASSWORD:-}"
DB=""
ONE_COLL=""
JSON=0
TOAST_RATIO="0.5"
MIN_TOTAL_KB="256"
FIELD_MIN_BYTES="1024"
SAMPLE="100"
TOAST_INLINE_THRESHOLD="2000"   # PostgreSQL TOAST_TUPLE_THRESHOLD ~= 2 KB

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db)             DB="$2"; shift 2;;
        --collection)     ONE_COLL="$2"; shift 2;;
        --container)      CONTAINER_NAME="$2"; shift 2;;
        --port)           PORT="$2"; shift 2;;
        --pg-port)        PG_PORT="$2"; shift 2;;
        --password)       PASSWORD="$2"; shift 2;;
        --toast-ratio)    TOAST_RATIO="$2"; shift 2;;
        --min-total-kb)   MIN_TOTAL_KB="$2"; shift 2;;
        --field-min-bytes)FIELD_MIN_BYTES="$2"; shift 2;;
        --sample)         SAMPLE="$2"; shift 2;;
        --json)           JSON=1; shift;;
        -h|--help)        sed -n '2,44p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
        *)                echo "Unknown option: $1" >&2; exit 2;;
    esac
done
[[ -z "$DB" ]] && { echo "Error: --db <name> is required" >&2; exit 1; }
[[ -z "$PASSWORD" ]] && { echo "Error: no password. Set DB_PASSWORD or pass --password (e.g. export DB_PASSWORD='<your-password>')." >&2; exit 1; }

run_mongosh() {
    docker exec "$CONTAINER_NAME" mongosh "localhost:${PORT}/${DB}" \
        -u "$DB_USER_" -p "$PASSWORD" --authenticationMechanism SCRAM-SHA-256 \
        --tls --tlsAllowInvalidCertificates --quiet --eval "$1" 2>/dev/null
}
run_psql() {
    docker exec "$CONTAINER_NAME" psql -h localhost -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
        -t --no-align -F $'\t' -c "$1" 2>/dev/null | grep -vE '^(SET|)$'
}

# ── Per-collection heap/TOAST from PostgreSQL (measured facts) ──────────────
# tab-separated: collection<TAB>heap_bytes<TAB>toast_bytes<TAB>total_bytes
COLL_FILTER=""
[[ -n "$ONE_COLL" ]] && COLL_FILTER="AND c.collection_name = '${ONE_COLL}'"
SIZES=$(run_psql "
SELECT c.collection_name,
       pg_relation_size(t.oid),
       COALESCE(pg_relation_size(NULLIF(t.reltoastrelid,0)),0),
       pg_total_relation_size(t.oid)
FROM documentdb_api_catalog.collections c
JOIN pg_class t ON t.oid = ('documentdb_data.documents_' || c.collection_id)::regclass
WHERE c.database_name = '${DB}' ${COLL_FILTER}
ORDER BY pg_total_relation_size(t.oid) DESC;
")

if [[ -z "$SIZES" ]]; then
    echo "No collections found for database '${DB}' (is it seeded? is the container up?)" >&2
    exit 1
fi

# ── Sample per-field average size for a collection (mongosh) ────────────────
# Emits one line:  FIELDJSON {"avg_obj_size":N,"sampled":M,"fields":[{"f":..,"b":..},...]}
# NOTE: JSON.stringify length approximates the serialized field size; it is used
# for RANKING split candidates, not as an exact byte count.
field_json() {
    local coll="$1"
    run_mongosh '
        var s = db.'"$coll"'.stats();
        var avg = s.avgObjSize || 0;
        var docs = db.'"$coll"'.aggregate([{$sample:{size:'"$SAMPLE"'}}]).toArray();
        var acc = {}, n = docs.length || 1;
        docs.forEach(function(doc){
            Object.keys(doc).forEach(function(k){
                if (k === "_id") return;
                var len = 0; try { len = JSON.stringify(doc[k]).length; } catch(e) { len = 0; }
                acc[k] = (acc[k]||0) + len;
            });
        });
        var fields = Object.keys(acc).map(function(k){ return {f:k, b:Math.round(acc[k]/n)}; });
        fields.sort(function(a,b){ return b.b - a.b; });
        print("FIELDJSON " + JSON.stringify({avg_obj_size: avg, sampled: n, fields: fields}));
    ' | sed -n 's/^FIELDJSON //p'
}

# ── Collect one record per collection into a buffer for a single Python pass ─
# line format:  coll<TAB>heap<TAB>toast<TAB>total<TAB>(FIELDJSON | CLEAN)
BUFFER=""
while IFS=$'\t' read -r coll heap toast total; do
    [[ -z "$coll" ]] && continue
    # strip any stray non-digits (e.g. trailing CR) so arithmetic is reliable
    heap="${heap//[!0-9]/}";  toast="${toast//[!0-9]/}";  total="${total//[!0-9]/}"
    heap="${heap:-0}"; toast="${toast:-0}"; total="${total:-0}"
    (( total < MIN_TOTAL_KB * 1024 )) && continue
    ratio=$(awk -v t="$toast" -v h="$heap" 'BEGIN{ d=t+h; if(d<=0){print 0}else{printf "%.4f", t/d} }')
    over=$(awk -v r="$ratio" -v thr="$TOAST_RATIO" 'BEGIN{ print (r>thr)?1:0 }')
    if [[ "$over" == "1" ]]; then
        fj=$(field_json "$coll")
        [[ -z "$fj" ]] && fj='{"avg_obj_size":0,"sampled":0,"fields":[]}'
        BUFFER+="${coll}"$'\t'"${heap}"$'\t'"${toast}"$'\t'"${total}"$'\t'"${fj}"$'\n'
    else
        BUFFER+="${coll}"$'\t'"${heap}"$'\t'"${toast}"$'\t'"${total}"$'\t'"CLEAN"$'\n'
    fi
done <<< "$SIZES"

if [[ "${DEBUG:-0}" == "1" ]]; then
    { echo "── DEBUG: SIZES rows ──"; printf '%s\n' "$SIZES" | cat -A
      echo "── DEBUG: BUFFER ──"; printf '%s' "$BUFFER" | cat -A; } >&2
fi

# ── Build the report in Python (robust JSON assembly + float math) ──────────
REPORT_DATA="$BUFFER" JSON_MODE="$JSON" DB_NAME="$DB" \
FIELD_MIN="$FIELD_MIN_BYTES" INLINE_THR="$TOAST_INLINE_THRESHOLD" \
TOAST_RATIO="$TOAST_RATIO" MIN_KB="$MIN_TOTAL_KB" \
python3 "$SCRIPT_DIR/toast-split-advisor-render.py"
