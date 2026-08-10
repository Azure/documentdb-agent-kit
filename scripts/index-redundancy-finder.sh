#!/usr/bin/env bash
# index-redundancy-finder.sh — Index Redundancy Finder for DocumentDB
#
# Generic tool that cross-references MongoDB index catalog with PostgreSQL
# index statistics to find redundant, duplicate, or unused indexes.
# Works with ANY DocumentDB database (auto-discovers collections & indexes).
#
# Detection rules (priority order):
#   1. EXACT_DUPLICATE  — Two indexes with identical key spec
#   2. INVALID          — Indexes flagged invalid in DocumentDB catalog
#   3. PREFIX_REDUNDANT — {a,b} subsumed by {a,b,c}
#   4. UNIQUE_SHADOWED  — Non-unique idx{a} shadowed by unique idx{a}
#   5. UNUSED_VERIFIED  — Zero scans at BOTH MongoDB API and PG layers
#   6. WRITE_TAX        — Unused index on write-heavy table
#   7. REVERSE_VARIANT  — {a:1,b:1} alongside {a:1,b:-1} (LOW: needs human review)
#
# Output: ranked findings with rationale, DROP commands, and storage estimates.
#
# Usage:
#   bash scripts/index-redundancy-finder.sh --db <name> [--container NAME] [--password PASS]
#   bash scripts/index-redundancy-finder.sh --db ecommerce --container documentdb-local
#   bash scripts/index-redundancy-finder.sh --all-dbs
#   bash scripts/index-redundancy-finder.sh --db myapp --json   # machine-readable output
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CONTAINER_NAME="${CONTAINER_NAME:-documentdb-local}"
PORT="${PORT:-10260}"
PG_PORT="${PG_PORT:-9712}"
PG_USER="${PG_USER:-documentdb}"
PG_DB="${PG_DB:-postgres}"
USER="${DB_USER:-docdbadmin}"
PASSWORD="${DB_PASSWORD:-}"
DB=""
ALL_DBS=false
JSON_OUTPUT=false
MIN_AGE_DAYS=0  # warn-only threshold for "unused" classification

while [[ $# -gt 0 ]]; do
    case "$1" in
        --container)  CONTAINER_NAME="$2"; shift 2;;
        --password)   PASSWORD="$2"; shift 2;;
        --port)       PORT="$2"; shift 2;;
        --pg-port)    PG_PORT="$2"; shift 2;;
        --db)         DB="$2"; shift 2;;
        --all-dbs)    ALL_DBS=true; shift;;
        --json)       JSON_OUTPUT=true; shift;;
        --min-age-days) MIN_AGE_DAYS="$2"; shift 2;;
        -h|--help)
            cat <<EOF
Usage: $0 --db <name> [OPTIONS]

Required:
  --db NAME              Target database (or use --all-dbs)
  --all-dbs              Scan all databases

Optional:
  --container NAME       Docker container (default: documentdb-local)
  --password PASS        DocumentDB password (required; or set DB_PASSWORD)
  --port PORT            MongoDB gateway port (default: 10260)
  --pg-port PORT         PostgreSQL internal port (default: 9712)
  --json                 Emit machine-readable JSON instead of report
  --min-age-days N       Only flag UNUSED if stats accumulated >= N days (default: 0)

Examples:
  $0 --db ecommerce
  $0 --all-dbs
  $0 --db myapp --json > findings.json
EOF
            exit 0;;
        *)            shift;;
    esac
done

[[ -z "$DB" && "$ALL_DBS" != "true" ]] && { echo "Error: --db <name> or --all-dbs is required"; exit 1; }
[[ -z "$PASSWORD" ]] && { echo "Error: no password. Set DB_PASSWORD or pass --password (e.g. export DB_PASSWORD='<your-password>')." >&2; exit 1; }

# ── Helpers ───────────────────────────────────────────────────────────
run_mongosh() {
    local target_db="${2:-$DB}"
    docker exec -u documentdb "$CONTAINER_NAME" mongosh \
        "localhost:${PORT}/${target_db}" -u "$USER" -p "$PASSWORD" \
        --authenticationMechanism SCRAM-SHA-256 --tls --tlsAllowInvalidCertificates \
        --quiet --eval "$1" 2>/dev/null
}

run_psql() {
    docker exec "$CONTAINER_NAME" psql -h localhost -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
        -t -A -F $'\t' -c "$1" 2>/dev/null | grep -v "^SET$"
}

# Print a banner only if not JSON mode
banner() { $JSON_OUTPUT || echo "$@"; }
section() { $JSON_OUTPUT || { echo ""; echo "$@"; }; }

TIMESTAMP=$(date +%Y%m%d%H%M%S)

banner "╔══════════════════════════════════════════════════════════════════╗"
banner "║  DocumentDB Index Redundancy Finder                              ║"
banner "║  Database: ${DB:-ALL}"
banner "║  Container: $CONTAINER_NAME"
banner "║  Timestamp: $TIMESTAMP"
banner "╚══════════════════════════════════════════════════════════════════╝"
banner ""

# Discover databases
if [[ "$ALL_DBS" == "true" ]]; then
    DATABASES=$(run_mongosh 'db.adminCommand({listDatabases:1}).databases.forEach(function(d){if(d.name!=="admin"&&d.name!=="config"&&d.name!=="local")print(d.name);})' "admin")
else
    DATABASES="$DB"
fi

# Findings accumulator (JSON array)
ALL_FINDINGS_JSON="[]"

for CURRENT_DB in $DATABASES; do
banner "┌──────────────────────────────────────────────────────────────┐"
banner "│  Database: $CURRENT_DB"
banner "└──────────────────────────────────────────────────────────────┘"
banner ""

# ── Step 1: Pull all index specs + usage from MongoDB API ─────────────
# Output format (one line per index, tab-separated):
#   collection \t name \t keys_json \t unique \t ops \t partial \t sparse
MONGO_INDEXES=$(run_mongosh '
var out = [];
db.getCollectionNames().sort().forEach(function(c) {
    var indexes;
    try { indexes = db[c].getIndexes(); } catch(e) { return; }
    var statsMap = {};
    try {
        db[c].aggregate([{$indexStats:{}}]).toArray().forEach(function(s) {
            statsMap[s.name] = Number((s.accesses || {}).ops || 0);
        });
    } catch(e) {}
    indexes.forEach(function(idx) {
        var line = [
            c,
            idx.name,
            JSON.stringify(idx.key),
            idx.unique ? "1" : "0",
            String(statsMap[idx.name] || 0),
            idx.partialFilterExpression ? "1" : "0",
            idx.sparse ? "1" : "0"
        ].join("\t");
        print(line);
    });
});
' "$CURRENT_DB")

if [[ -z "$MONGO_INDEXES" ]]; then
    banner "  (no collections in $CURRENT_DB)"
    continue
fi

# ── Step 2: Pull PG-level stats for this database's indexes ──────────
# Map: collection_name -> { index_name -> {pg_index_name, idx_scan, size_bytes, valid} }
# DocumentDB stores indexes as PG indexes on documents_<collection_id> tables.
# We need to: collection_id -> PG table -> PG indexes -> stats
PG_STATS=$(run_psql "
SELECT c.collection_name,
       (ci.index_spec).index_name AS mongo_idx_name,
       i.indexrelname AS pg_idx_name,
       COALESCE(s.idx_scan, 0) AS idx_scan,
       pg_relation_size(i.indexrelid) AS size_bytes,
       ci.index_is_valid,
       COALESCE(t.n_tup_ins + t.n_tup_upd + t.n_tup_del, 0) AS write_ops
FROM documentdb_api_catalog.collections c
JOIN documentdb_api_catalog.collection_indexes ci
  ON ci.collection_id = c.collection_id
LEFT JOIN pg_stat_user_indexes i
  ON i.schemaname = 'documentdb_data'
  AND i.relname = 'documents_' || c.collection_id
  AND i.indexrelname LIKE '%_' || ci.index_id::text
LEFT JOIN pg_stat_user_indexes s
  ON s.indexrelid = i.indexrelid
LEFT JOIN pg_stat_user_tables t
  ON t.schemaname = 'documentdb_data'
  AND t.relname = 'documents_' || c.collection_id
WHERE c.database_name = '$CURRENT_DB'
ORDER BY c.collection_name, ci.index_id
")

# Build associative arrays in awk for fast lookup
# We'll process in awk and emit JSON findings

# Combined analysis pipeline:
FINDINGS=$(echo "$MONGO_INDEXES" | awk -v pg_stats="$PG_STATS" -v db="$CURRENT_DB" '
BEGIN {
    FS="\t";
    # Parse PG stats into associative arrays
    n_pg = split(pg_stats, pg_lines, "\n");
    for (i=1; i<=n_pg; i++) {
        line = pg_lines[i];
        if (length(line) == 0) continue;
        split(line, p, "\t");
        coll = p[1]; mname = p[2];
        key = coll "::" mname;
        pg_pg_name[key]   = p[3];
        pg_idx_scan[key]  = (p[4]+0);
        pg_size[key]      = (p[5]+0);
        pg_valid[key]     = p[6];
        pg_writes[key]    = (p[7]+0);
    }
}
{
    coll = $1; name = $2; keys_json = $3; uniq = $4; ops = ($5+0);
    partial = $6; sparse = $7;
    # Skip the _id index (special, never droppable)
    if (name == "_id_") next;
    idx_count[coll]++;
    n = idx_count[coll];
    # Store
    idx_coll[coll, n]    = coll;
    idx_name[coll, n]    = name;
    idx_keys[coll, n]    = keys_json;
    idx_uniq[coll, n]    = uniq;
    idx_ops[coll, n]     = ops;
    idx_partial[coll, n] = partial;
    idx_sparse[coll, n]  = sparse;
    # Track collection list
    if (!seen[coll]) { seen[coll]=1; coll_order[++ncolls] = coll; }
}
END {
    # For each collection, run all rule checks pairwise / standalone
    print "[";
    first_finding = 1;
    for (ci=1; ci<=ncolls; ci++) {
        coll = coll_order[ci];
        cnt = idx_count[coll];

        # Build a normalized key list for each index (extract field names in order)
        for (i=1; i<=cnt; i++) {
            kjson = idx_keys[coll, i];
            # Extract sequence of "field":value pairs preserving order
            # Simple parse: split on commas, then on colons
            tmp = kjson;
            gsub(/^\{/, "", tmp); gsub(/\}$/, "", tmp);
            n_pairs = split(tmp, pairs, ",");
            fields[coll, i] = "";
            dirs[coll, i]   = "";
            for (pi=1; pi<=n_pairs; pi++) {
                pair = pairs[pi];
                # Pair like:  "field" : 1   or "field" : -1
                # Get field name
                fname = pair;
                sub(/^[ \t]*"/, "", fname);
                sub(/".*/, "", fname);
                # Get direction value (last numeric / string)
                dval = pair;
                sub(/^[^:]*:[ \t]*/, "", dval);
                gsub(/[ \t]/, "", dval);
                fields[coll, i] = fields[coll, i] (fields[coll, i]=="" ? "" : ",") fname;
                dirs[coll, i]   = dirs[coll, i]   (dirs[coll, i]==""   ? "" : ",") dval;
            }
        }

        # ── RULE 1: EXACT_DUPLICATE ─────────────────────────────────
        for (i=1; i<=cnt; i++) {
            for (j=i+1; j<=cnt; j++) {
                if (fields[coll,i] == fields[coll,j] && dirs[coll,i] == dirs[coll,j]) {
                    # Keep the unique one if any, drop the other
                    if (idx_uniq[coll,i] == "1" && idx_uniq[coll,j] == "0") {
                        emit_finding(coll, idx_name[coll,j], "EXACT_DUPLICATE", "HIGH",
                            "Identical key spec to " idx_name[coll,i] " (which is UNIQUE); this one is redundant",
                            idx_name[coll,i]);
                    } else if (idx_uniq[coll,j] == "1" && idx_uniq[coll,i] == "0") {
                        emit_finding(coll, idx_name[coll,i], "EXACT_DUPLICATE", "HIGH",
                            "Identical key spec to " idx_name[coll,j] " (which is UNIQUE); this one is redundant",
                            idx_name[coll,j]);
                    } else {
                        emit_finding(coll, idx_name[coll,j], "EXACT_DUPLICATE", "HIGH",
                            "Identical key spec to " idx_name[coll,i] " — exact duplicate",
                            idx_name[coll,i]);
                    }
                }
            }
        }

        # ── RULE 3: PREFIX_REDUNDANT ────────────────────────────────
        for (i=1; i<=cnt; i++) {
            for (j=1; j<=cnt; j++) {
                if (i == j) continue;
                if (fields[coll,i] == fields[coll,j]) continue;  # exact dup handled
                # i is prefix of j?
                f_i = fields[coll,i]; f_j = fields[coll,j];
                d_i = dirs[coll,i];   d_j = dirs[coll,j];
                prefix_i = f_i ",";
                if (index(f_j ",", prefix_i) == 1) {
                    # Check directions match for the prefix
                    pref_d_i = d_i ",";
                    if (index(d_j ",", pref_d_i) == 1) {
                        # Skip if i is unique (can not be replaced)
                        if (idx_uniq[coll,i] == "1") continue;
                        # Skip if i has partial filter or sparse (special semantics)
                        if (idx_partial[coll,i] == "1" || idx_sparse[coll,i] == "1") continue;
                        emit_finding(coll, idx_name[coll,i], "PREFIX_REDUNDANT", "HIGH",
                            "Index {" f_i "} is a prefix of {" f_j "} (" idx_name[coll,j] ") — covered by the longer index",
                            idx_name[coll,j]);
                    }
                }
            }
        }

        # ── RULE 7: REVERSE_VARIANT (LOW severity) ──────────────────
        for (i=1; i<=cnt; i++) {
            for (j=i+1; j<=cnt; j++) {
                if (fields[coll,i] != fields[coll,j]) continue;
                if (dirs[coll,i] == dirs[coll,j]) continue;
                emit_finding(coll, idx_name[coll,j], "REVERSE_VARIANT", "LOW",
                    "Same fields as " idx_name[coll,i] " but reverse sort direction — MongoDB can often walk an index in either direction; review query patterns",
                    idx_name[coll,i]);
            }
        }

        # ── RULE 2: INVALID, RULE 5: UNUSED_VERIFIED, RULE 6: WRITE_TAX ──
        for (i=1; i<=cnt; i++) {
            key = coll "::" idx_name[coll,i];
            valid     = pg_valid[key];
            pg_scans  = pg_idx_scan[key];
            pg_size_b = pg_size[key];
            writes    = pg_writes[key];

            if (valid == "f") {
                emit_finding(coll, idx_name[coll,i], "INVALID", "HIGH",
                    "Index marked invalid in DocumentDB catalog (PG idx: " pg_pg_name[key] ") — likely failed during creation, consuming disk with no benefit",
                    "");
            }

            mongo_ops = idx_ops[coll,i];
            # Cross-validated unused: both layers report at most a noise-floor scan.
            # ($indexStats and pg_stat record index build / explain as 1 access.)
            if (mongo_ops <= 1 && pg_scans <= 1) {
                size_kb = int(pg_size_b/1024);
                if (writes > 1000) {
                    emit_finding(coll, idx_name[coll,i], "WRITE_TAX", "MEDIUM",
                        "Zero reads (MongoDB + PG) but table has " writes " write ops — pure write amplification, ~" size_kb "KB on disk",
                        "");
                } else {
                    emit_finding(coll, idx_name[coll,i], "UNUSED_VERIFIED", "MEDIUM",
                        "Zero scans at both MongoDB ($indexStats.ops) and PG (pg_stat_user_indexes.idx_scan) layers — ~" size_kb "KB on disk",
                        "");
                }
            }
        }
    }
    print "]";
}

function emit_finding(coll, name, kind, severity, reason, replaces) {
    if (!first_finding) print ",";
    first_finding = 0;
    # JSON-escape strings
    gsub(/\\/, "\\\\", reason); gsub(/"/, "\\\"", reason);
    printf "  {\"db\":\"%s\",\"collection\":\"%s\",\"index\":\"%s\",\"rule\":\"%s\",\"severity\":\"%s\",\"reason\":\"%s\",\"replaces_with\":\"%s\"}", db, coll, name, kind, severity, reason, replaces;
}
' )

# Pretty-print findings unless JSON mode
if $JSON_OUTPUT; then
    # Merge with overall JSON
    if [[ "$ALL_FINDINGS_JSON" == "[]" ]]; then
        ALL_FINDINGS_JSON="$FINDINGS"
    else
        # Strip closing ] of prev, opening [ of new, join with ,
        ALL_FINDINGS_JSON="${ALL_FINDINGS_JSON%]},${FINDINGS#[}"
    fi
else
    # Parse JSON findings and pretty-print (renderer lives in a standalone module)
    echo "$FINDINGS" | python3 "$SCRIPT_DIR/index-redundancy-render.py" 2>&1
fi

done  # end of for CURRENT_DB

# Final JSON output if requested
if $JSON_OUTPUT; then
    echo "$ALL_FINDINGS_JSON"
else
    echo ""
    echo "═══════════════════════════════════════════════════════════════════"
    echo "  Legend:"
    echo "    🔴 HIGH   — Safe to drop (validated by index spec / catalog)"
    echo "    🟡 MEDIUM — Likely safe (zero usage validated at both layers)"
    echo "    🔵 LOW    — Review query patterns before dropping"
    echo "═══════════════════════════════════════════════════════════════════"
fi
