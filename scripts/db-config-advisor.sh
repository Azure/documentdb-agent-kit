#!/usr/bin/env bash
# db-config-advisor.sh — Evidence-based configuration & cache advisor for DocumentDB.
#
# Reports MEASURED facts and ties every observation to a number. It does NOT
# emit generic rules-of-thumb ("set shared_buffers to 25% of RAM"). Instead it
# computes, for a target database:
#   - the WORKING SET   = bytes that must be cached for this workload to be
#                         memory-resident (heap + TOAST + indexes of its tables)
#   - the current shared_buffers / effective_cache_size (factual, with source)
#   - the MEASURED buffer-cache hit ratios (heap / TOAST / index) from pg_statio
#   - the TOAST share of the working set (links to document-bloat-advisor)
# and states the evidence-derived implication (e.g. "working set is 4.1x
# shared_buffers and TOAST is 92% of it; shrinking documents or raising
# shared_buffers toward the measured working set would improve residency").
#
# Usage:
#   bash scripts/db-config-advisor.sh --db <name> [--json]
#     [--container NAME] [--pg-port 9712]
#
# Read-only: this tool only SELECTs from pg_statio_* / pg_settings / catalog views;
# it never resets statistics or alters any database state. Cache-hit ratios are
# cumulative since the server's stats were last reset. If you want a clean
# measurement window, reset stats yourself out-of-band (e.g. psql
# "SELECT pg_stat_reset()"), run your workload, then re-run this tool.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/diagnostic-runtime.sh"

CONTAINER_NAME="${CONTAINER_NAME:-documentdb-local}"
PG_PORT="${PG_PORT:-9712}"
PG_USER="${PG_USER:-documentdb}"
PG_DB="${PG_DB:-postgres}"
DB=""
JSON=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db)         DB="$2"; shift 2;;
        --container)  CONTAINER_NAME="$2"; shift 2;;
        --pg-port)    PG_PORT="$2"; shift 2;;
        --json)       JSON=1; shift;;
        -h|--help)    sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
        *)            echo "Unknown option: $1" >&2; exit 2;;
    esac
done
[[ -z "$DB" ]] && { echo "Error: --db <name> is required" >&2; exit 1; }

run_psql() {
    docdb_exec_as "" psql -h localhost -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
        -t --no-align -F $'\t' -c "$1" 2>/dev/null | grep -vE '^SET$'
}

# ── Config (factual) ────────────────────────────────────────────────────────
SB_BYTES=$(run_psql "SELECT pg_size_bytes(current_setting('shared_buffers'))")
EC_BYTES=$(run_psql "SELECT pg_size_bytes(current_setting('effective_cache_size'))")
SB_H=$(run_psql "SELECT pg_size_pretty(pg_size_bytes(current_setting('shared_buffers')))")
EC_H=$(run_psql "SELECT pg_size_pretty(pg_size_bytes(current_setting('effective_cache_size')))")
SB_SRC=$(run_psql "SELECT source FROM pg_settings WHERE name='shared_buffers'")

# ── Working set for this DB (heap+toast+indexes of its collections) ──────────
# returns: total_bytes<TAB>heap_bytes<TAB>toast_bytes<TAB>index_bytes
WS=$(run_psql "
WITH tabs AS (
  SELECT ('documentdb_data.documents_'||c.collection_id)::regclass AS oid
  FROM documentdb_api_catalog.collections c
  WHERE c.database_name = '${DB}'
)
SELECT
  COALESCE(SUM(pg_total_relation_size(oid)),0),
  COALESCE(SUM(pg_relation_size(oid)),0),
  COALESCE(SUM(pg_relation_size(NULLIF((SELECT reltoastrelid FROM pg_class WHERE pg_class.oid=tabs.oid),0))),0),
  COALESCE(SUM(pg_indexes_size(oid)),0)
FROM tabs;
")
WS_TOTAL=$(echo "$WS" | cut -f1); WS_HEAP=$(echo "$WS" | cut -f2)
WS_TOAST=$(echo "$WS" | cut -f3); WS_IDX=$(echo "$WS" | cut -f4)
[[ -z "$WS_TOTAL" || "$WS_TOTAL" == "0" ]] && { echo "No collections for '${DB}' (seeded? container up?)" >&2; exit 1; }

# ── Measured cache-hit ratios (pg_statio, this DB's tables) ──────────────────
# returns: heap_hit<TAB>heap_read<TAB>toast_hit<TAB>toast_read<TAB>idx_hit<TAB>idx_read
IO=$(run_psql "
SELECT COALESCE(SUM(s.heap_blks_hit),0), COALESCE(SUM(s.heap_blks_read),0),
       COALESCE(SUM(s.toast_blks_hit),0), COALESCE(SUM(s.toast_blks_read),0),
       COALESCE(SUM(s.idx_blks_hit),0),  COALESCE(SUM(s.idx_blks_read),0)
FROM pg_statio_user_tables s
JOIN documentdb_api_catalog.collections c
  ON s.relname = 'documents_' || c.collection_id
WHERE s.schemaname='documentdb_data' AND c.database_name='${DB}';
")
HH=$(echo "$IO"|cut -f1); HR=$(echo "$IO"|cut -f2); TH=$(echo "$IO"|cut -f3)
TR=$(echo "$IO"|cut -f4); IH=$(echo "$IO"|cut -f5); IR=$(echo "$IO"|cut -f6)

pct() { awk -v h="$1" -v r="$2" 'BEGIN{ d=h+r; if(d<=0){print "n/a"}else{printf "%.1f%%", 100*h/d} }'; }
ratio_x() { awk -v a="$1" -v b="$2" 'BEGIN{ if(b<=0){print "n/a"}else{printf "%.1fx", a/b} }'; }
mb() { awk -v b="$1" 'BEGIN{ printf "%.1f", b/1048576 }'; }
share() { awk -v a="$1" -v b="$2" 'BEGIN{ if(b<=0){print "0"}else{printf "%.0f", 100*a/b} }'; }

HEAP_HIT=$(pct "$HH" "$HR"); TOAST_HIT=$(pct "$TH" "$TR"); IDX_HIT=$(pct "$IH" "$IR")
WS_VS_SB=$(ratio_x "$WS_TOTAL" "$SB_BYTES")
TOAST_SHARE=$(share "$WS_TOAST" "$WS_TOTAL")
WS_MINUS_TOAST=$(( WS_TOTAL - WS_TOAST ))
WS_MINUS_TOAST_VS_SB=$(ratio_x "$WS_MINUS_TOAST" "$SB_BYTES")

if [[ "$JSON" == "1" ]]; then
    printf '{'
    printf '"db":"%s",' "$DB"
    printf '"shared_buffers_bytes":%s,"shared_buffers_source":"%s",' "$SB_BYTES" "$SB_SRC"
    printf '"effective_cache_size_bytes":%s,' "$EC_BYTES"
    printf '"working_set_bytes":%s,"working_set_heap_bytes":%s,"working_set_toast_bytes":%s,"working_set_index_bytes":%s,' "$WS_TOTAL" "$WS_HEAP" "$WS_TOAST" "$WS_IDX"
    printf '"working_set_vs_shared_buffers":"%s","toast_share_pct":%s,"working_set_minus_toast_vs_shared_buffers":"%s",' "$WS_VS_SB" "$TOAST_SHARE" "$WS_MINUS_TOAST_VS_SB"
    printf '"cache_hit_heap":"%s","cache_hit_toast":"%s","cache_hit_index":"%s",' "$HEAP_HIT" "$TOAST_HIT" "$IDX_HIT"
    printf '"toast_blks_read":%s,"heap_blks_read":%s' "$TR" "$HR"
    printf '}\n'
    exit 0
fi

echo "══════════════════════════════════════════════════════════════════"
echo " DocumentDB Config & Cache Advisor (evidence-based)"
echo " Database: ${DB}"
echo "══════════════════════════════════════════════════════════════════"
echo ""
echo " Configuration (factual):"
echo "   shared_buffers        = ${SB_H}  (source: ${SB_SRC})"
echo "   effective_cache_size  = ${EC_H}"
echo ""
echo " Working set for '${DB}' (must be cached to avoid disk I/O):"
echo "   total  = $(mb "$WS_TOTAL") MB   (heap $(mb "$WS_HEAP") + TOAST $(mb "$WS_TOAST") + idx $(mb "$WS_IDX"))"
echo "   vs shared_buffers     = ${WS_VS_SB}"
echo "   TOAST share of working set = ${TOAST_SHARE}%"
echo ""
echo " Measured buffer-cache hit ratio (pg_statio, cumulative):"
echo "   heap  = ${HEAP_HIT}    (read ${HR} blocks from disk)"
echo "   TOAST = ${TOAST_HIT}    (read ${TR} blocks from disk)"
echo "   index = ${IDX_HIT}"
echo ""
echo " Evidence-based observations:"
awk -v ws="$WS_TOTAL" -v sb="$SB_BYTES" 'BEGIN{ if(sb>0 && ws>sb) print "   • Working set ('"$(mb "$WS_TOTAL")"'MB) EXCEEDS shared_buffers ('"$SB_H"') by '"$WS_VS_SB"'."; else print "   • Working set fits within shared_buffers." }'
if [[ "$TOAST_SHARE" -ge 50 ]]; then
    echo "   • TOAST is ${TOAST_SHARE}% of the working set. This is large-text bloat:"
    echo "     removing it (schema split — see document-bloat-advisor) would cut the"
    echo "     working set to $(mb "$WS_MINUS_TOAST") MB (${WS_MINUS_TOAST_VS_SB} shared_buffers),"
    echo "     letting the hot data stay resident WITHOUT changing config."
fi
awk -v tr="$TR" 'BEGIN{ if(tr>0) print "   • TOAST blocks are being read from disk — detoasting large text is"; }'
awk -v tr="$TR" 'BEGIN{ if(tr>0) print "     causing physical I/O, not just cache churn."; }'
echo ""
echo " Note: recommendations are derived from the measured working set and hit"
echo "       ratios above — not from generic rules of thumb. Prefer shrinking the"
echo "       working set (document-bloat-advisor) before raising shared_buffers."
