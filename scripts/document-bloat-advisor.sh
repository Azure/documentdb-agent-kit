#!/usr/bin/env bash
# document-bloat-advisor.sh — DocumentDB large-document / TOAST tax advisor.
#
# DocumentDB stores each document as a single BSON column in PostgreSQL. When a
# document carries a large, low-compressibility field (long text, blobs), that
# value is pushed out-of-line into a TOAST table. Because the whole document is
# ONE column, reading ANY scalar field detoasts the ENTIRE document — so
# co-locating big text with fields your queries scan/aggregate imposes a
# per-access "detoast tax": huge extra I/O and buffer-cache pollution that never
# shows up as a missing index.
#
# This tool MEASURES that condition (no guessing):
#   - per-collection heap vs TOAST bytes (PostgreSQL, cross-layer)
#   - MongoDB avgObjSize
#   - which top-level fields dominate document size (sampled)
# and recommends the DocumentDB-specific fix: SPLIT the large field(s) into a
# side collection keyed by _id, so the hot collection stays small/inline.
#
# Note: projection alone does NOT avoid the tax — the document is detoasted
# server-side before projection is applied. The fix is schema separation.
#
# Usage:
#   bash scripts/document-bloat-advisor.sh --db <name> [--json]
#     [--container NAME] [--port 10260] [--pg-port 9712]
#     [--toast-ratio 0.5]     flag when TOAST/(heap+TOAST) exceeds this
#     [--min-total-kb 256]    ignore collections smaller than this
set -uo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-documentdb-local}"
PORT="${PORT:-10260}"
PG_PORT="${PG_PORT:-9712}"
PG_USER="${PG_USER:-documentdb}"
PG_DB="${PG_DB:-postgres}"
DB_USER_="${DB_USER:-docdbadmin}"
PASSWORD="${DB_PASSWORD:-}"
DB=""
JSON=0
TOAST_RATIO="0.5"
MIN_TOTAL_KB="256"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db)          DB="$2"; shift 2;;
        --container)   CONTAINER_NAME="$2"; shift 2;;
        --port)        PORT="$2"; shift 2;;
        --pg-port)     PG_PORT="$2"; shift 2;;
        --password)    PASSWORD="$2"; shift 2;;
        --toast-ratio) TOAST_RATIO="$2"; shift 2;;
        --min-total-kb)MIN_TOTAL_KB="$2"; shift 2;;
        --json)        JSON=1; shift;;
        -h|--help)     sed -n '2,33p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
        *)             echo "Unknown option: $1" >&2; exit 2;;
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
SIZES=$(run_psql "
SELECT c.collection_name,
       pg_relation_size(t.oid),
       COALESCE(pg_relation_size(NULLIF(t.reltoastrelid,0)),0),
       pg_total_relation_size(t.oid)
FROM documentdb_api_catalog.collections c
JOIN pg_class t ON t.oid = ('documentdb_data.documents_' || c.collection_id)::regclass
WHERE c.database_name = '${DB}'
ORDER BY pg_total_relation_size(t.oid) DESC;
")

if [[ -z "$SIZES" ]]; then
    echo "No collections found for database '${DB}' (is it seeded? is the container up?)" >&2
    exit 1
fi

# ── Analyze each collection; sample dominant fields for flagged ones ────────
emit_human() { [[ "$JSON" == "0" ]] && echo "$1"; }

emit_human "══════════════════════════════════════════════════════════════════"
emit_human " DocumentDB Large-Document / TOAST Advisor"
emit_human " Database: ${DB}    (flag TOAST ratio > ${TOAST_RATIO}, min ${MIN_TOTAL_KB}KB)"
emit_human "══════════════════════════════════════════════════════════════════"
emit_human ""

FINDINGS_JSON="["
first=1
flagged=0
total_toast=0

while IFS=$'\t' read -r coll heap toast total; do
    [[ -z "$coll" ]] && continue
    total_kb=$(( total / 1024 ))
    (( total < MIN_TOTAL_KB * 1024 )) && continue
    # toast ratio via awk (float)
    ratio=$(awk -v t="$toast" -v h="$heap" 'BEGIN{ d=t+h; if(d<=0){print 0}else{printf "%.3f", t/d} }')
    over=$(awk -v r="$ratio" -v thr="$TOAST_RATIO" 'BEGIN{ print (r>thr)?1:0 }')

    heap_kb=$(( heap / 1024 )); toast_kb=$(( toast / 1024 ))

    if [[ "$over" == "1" ]]; then
        flagged=$((flagged+1))
        total_toast=$(( total_toast + toast ))
        # MongoDB avgObjSize + dominant top-level fields (sampled)
        FIELDS=$(run_mongosh '
            var s = db.'"$coll"'.stats();
            var avg = s.avgObjSize || 0;
            var docs = db.'"$coll"'.aggregate([{$sample:{size:20}}]).toArray();
            var acc = {};
            docs.forEach(function(doc){
                Object.keys(doc).forEach(function(k){
                    if (k==="_id") return;
                    var len = 0;
                    try { len = JSON.stringify(doc[k]).length; } catch(e) { len = 0; }
                    acc[k] = (acc[k]||0) + len;
                });
            });
            var n = docs.length || 1;
            var arr = Object.keys(acc).map(function(k){ return {f:k, avg:Math.round(acc[k]/n)}; });
            arr.sort(function(a,b){ return b.avg - a.avg; });
            print("AVG " + avg);
            arr.slice(0,3).forEach(function(x){ print("FLD " + x.f + " " + x.avg); });
        ')
        avgobj=$(echo "$FIELDS" | awk '/^AVG/{print $2}')
        bigfields=$(echo "$FIELDS" | awk '/^FLD/{print $2":"$3"B"}' | paste -sd, -)
        topfield=$(echo "$FIELDS" | awk '/^FLD/{print $2; exit}')

        emit_human "  ⚠️  ${coll}"
        emit_human "        heap=${heap_kb}KB  TOAST=${toast_kb}KB  (TOAST ratio ${ratio})  avgObjSize=${avgobj}B"
        emit_human "        dominant fields: ${bigfields}"
        emit_human "        → detoast tax: any scan/aggregate over ${coll} reads the full"
        emit_human "          document incl. the big text. Fix (DocumentDB-specific): move"
        emit_human "          '${topfield}' (and other large text) into a side collection"
        emit_human "          '${coll}_text' keyed by _id; keep ${coll} scalar-only."
        emit_human ""

        # JSON finding
        [[ $first -eq 0 ]] && FINDINGS_JSON+=","
        first=0
        FINDINGS_JSON+=$(printf '{"collection":"%s","heap_bytes":%s,"toast_bytes":%s,"toast_ratio":%s,"avg_obj_size":%s,"dominant_fields":"%s","recommended_split_field":"%s","fix":"move large text to side collection %s_text keyed by _id"}' \
            "$coll" "$heap" "$toast" "$ratio" "${avgobj:-0}" "$bigfields" "$topfield" "$coll")
    else
        emit_human "  ✅  ${coll}  heap=${heap_kb}KB TOAST=${toast_kb}KB (ratio ${ratio}) — no bloat"
    fi
done <<< "$SIZES"

FINDINGS_JSON+="]"

if [[ "$JSON" == "1" ]]; then
    echo "$FINDINGS_JSON"
    exit 0
fi

emit_human "──────────────────────────────────────────────────────────────────"
if [[ "$flagged" -eq 0 ]]; then
    emit_human "  ✅ No large-document/TOAST bloat detected."
else
    emit_human "  Flagged ${flagged} collection(s); $(( total_toast/1024 ))KB of TOASTed text"
    emit_human "  is detoasted on every scan of those collections."
    emit_human ""
    emit_human "  Why this is DocumentDB-specific: the whole document is one BSON column,"
    emit_human "  so reading any field detoasts the entire document. Projection does NOT"
    emit_human "  help (it runs after detoast). Splitting the large text into a side"
    emit_human "  collection keeps the hot documents small and inline."
fi
