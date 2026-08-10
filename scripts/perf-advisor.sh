#!/usr/bin/env bash
# perf-advisor.sh — Local Performance Advisor for DocumentDB
#
# Generic performance analysis tool that works with ANY DocumentDB database.
# Combines MongoDB-level diagnostics with deep PostgreSQL-level analysis
# (DocumentDB is built on PostgreSQL).
#
# Layer 1 — MongoDB API Layer (via mongosh):
#   1. Database overview (collection sizes, index counts)
#   2. Index health (unused, redundant/overlapping, missing)
#   3. Collection scan audit (auto-discovers query patterns, flags COLLSCAN)
#   4. Query performance profiling (times representative queries)
#
# Layer 2 — PostgreSQL Engine Layer (via psql):
#   5. PG table I/O stats (sequential vs index scans, cache hit rates)
#   6. PG index efficiency (unused PG indexes, bloat indicators)
#   7. Buffer cache analysis (heap + index hit rates per table)
#   8. PG connection & lock analysis
#   9. PG configuration (current settings — FACTUAL only)
#   10. Collection-ID mapping (MongoDB name ↔ PG table)
#
# Principle: this advisor reports MEASURED facts and concrete structural issues
# (scan/cache/lock counters, unused & redundant indexes, full scans with no
# covering index). It deliberately does NOT prescribe generic tuning values
# (e.g. "set shared_buffers to 25% of RAM") — such rules-of-thumb are not
# derived from your workload, can regress performance, and second-guess the
# tuned defaults DocumentDB ships. Tune from your own measured evidence.
#
# Usage:
#   bash scripts/perf-advisor.sh --db <name> [--container NAME] [--password PASS]
#   bash scripts/perf-advisor.sh --db ecommerce --container documentdb-local
#   bash scripts/perf-advisor.sh --db myapp --all-dbs  # scan all databases
set -uo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-documentdb-local}"
PORT="${PORT:-10260}"
PG_PORT="${PG_PORT:-9712}"
PG_USER="${PG_USER:-documentdb}"
PG_DB="${PG_DB:-postgres}"
USER="${DB_USER:-docdbadmin}"
PASSWORD="${DB_PASSWORD:-}"
DB=""
ALL_DBS=false
JSON=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --container)  CONTAINER_NAME="$2"; shift 2;;
        --password)   PASSWORD="$2"; shift 2;;
        --port)       PORT="$2"; shift 2;;
        --pg-port)    PG_PORT="$2"; shift 2;;
        --db)         DB="$2"; shift 2;;
        --all-dbs)    ALL_DBS=true; shift;;
        --json)       JSON=1; shift;;
        -h|--help)
            cat <<EOF
Usage: $0 --db <name> [OPTIONS]

Options:
  --db NAME         Target database (required unless --all-dbs)
  --all-dbs         Scan all databases
  --container NAME  Docker container name (default: documentdb-local)
  --password PASS   DocumentDB password (required; or set DB_PASSWORD)
  --port PORT       DocumentDB gateway port (default: 10260)
  --pg-port PORT    PostgreSQL internal port (default: 9712)
  --json            Emit a compact JSON findings summary only (no human report)
EOF
            exit 0;;
        *)            shift;;
    esac
done

[[ -z "$DB" && "$ALL_DBS" != "true" ]] && { echo "Error: --db <name> or --all-dbs is required"; exit 1; }
[[ -z "$PASSWORD" ]] && { echo "Error: no password. Set DB_PASSWORD or pass --password (e.g. export DB_PASSWORD='<your-password>')." >&2; exit 1; }

# ── Helper functions ──────────────────────────────────────────────────
run_mongosh() {
    local target_db="${2:-$DB}"
    docker exec -u documentdb "$CONTAINER_NAME" mongosh \
        "localhost:${PORT}/${target_db}" -u "$USER" -p "$PASSWORD" \
        --authenticationMechanism SCRAM-SHA-256 --tls --tlsAllowInvalidCertificates \
        --quiet --eval "$1" 2>/dev/null
}

run_psql() {
    docker exec "$CONTAINER_NAME" psql -h localhost -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
        -t --no-align -c "$1" 2>/dev/null
}

run_psql_pretty() {
    docker exec "$CONTAINER_NAME" psql -h localhost -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
        -c "$1" 2>/dev/null | grep -v "^SET$"
}

# psql that returns a single scalar/line with no formatting (for JSON assembly)
run_psql_raw() {
    docker exec "$CONTAINER_NAME" psql -h localhost -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
        -t -A -c "$1" 2>/dev/null
}

# human-only echo (suppressed in --json mode so stdout stays pure JSON)
hecho() { [[ "$JSON" == "1" ]] || echo "$@"; }

TIMESTAMP=$(date +%Y%m%d%H%M%S)

hecho "╔══════════════════════════════════════════════════════════════════╗"
hecho "║  DocumentDB Local Performance Advisor                          ║"
hecho "║  Database: ${DB:-ALL}"
hecho "║  Container: $CONTAINER_NAME"
hecho "║  Timestamp: $TIMESTAMP"
hecho "╚══════════════════════════════════════════════════════════════════╝"
hecho ""

# If --all-dbs, discover databases
if [[ "$ALL_DBS" == "true" ]]; then
    DATABASES=$(run_mongosh 'db.adminCommand({listDatabases:1}).databases.forEach(function(d){if(d.name!=="admin"&&d.name!=="config"&&d.name!=="local")print(d.name);})' "admin")
else
    DATABASES="$DB"
fi

# ══════════════════════════════════════════════════════════════════════
#  JSON MODE: emit a compact findings summary only, then exit
# ══════════════════════════════════════════════════════════════════════
if [[ "$JSON" == "1" ]]; then
    # Mongo-layer findings per database (index health, COLLSCAN audit, slow queries).
    read -r -d '' MONGO_JSON_JS <<'JS'
var out = { db: db.getName(), collections: [], index_health: [], collscans: [], slow_queries: [] };
var colls = db.getCollectionNames().sort();

// --- overview + index health ---
colls.forEach(function(c) {
    var st; try { st = db.runCommand({collStats: c}); } catch(e) { return; }
    out.collections.push({ name: c, docs: st.count||0, avg_obj_size: st.avgObjSize||0,
                           data_bytes: st.size||0, indexes: st.nindexes||0, index_bytes: st.totalIndexSize||0 });
    var indexes = db[c].getIndexes();
    var unused = [], redundant = [];
    if (indexes.length > 1) {
        try {
            db[c].aggregate([{$indexStats:{}}]).toArray().forEach(function(s) {
                if (s.name === "_id_") return;
                if ((s.accesses ? Number(s.accesses.ops) : 0) === 0) unused.push(s.name);
            });
        } catch(e) {}
        var ks = indexes.map(function(idx){ return {name: idx.name, keys: Object.keys(idx.key)}; });
        for (var i=0;i<ks.length;i++) for (var j=i+1;j<ks.length;j++) {
            var a=ks[i], b=ks[j];
            if (a.name==="_id_"||b.name==="_id_") continue;
            if (b.keys.length>a.keys.length && a.keys.every(function(k,ix){return k===b.keys[ix];}))
                redundant.push({prefix: a.name, of: b.name});
        }
    }
    if (unused.length || redundant.length) out.index_health.push({collection: c, unused: unused, redundant: redundant});
});

// --- COLLSCAN audit (same logic as the human report) ---
function effectiveIndex(node){ var g=0; while(node&&g++<50){ if(node.stage==="COLLSCAN")return "__COLLSCAN__"; if(node.stage==="IXSCAN")return node.indexName||"?"; node=node.inputStage||(node.inputStages?node.inputStages[0]:null);} return null; }
function testQuery(coll, field, label, filter, indexedFields){
    try {
        var plan = db.runCommand({explain:{find:coll, filter:filter, limit:1}, verbosity:"executionStats"});
        var wp=(plan.queryPlanner||{}).winningPlan||{}, es=plan.executionStats||{};
        var idx=effectiveIndex(wp), full=(idx==="__COLLSCAN__"||idx==="_id_");
        if (full && !(indexedFields && indexedFields[field]))
            out.collscans.push({collection: coll, query: label, docs_scanned: Number(es.totalDocsExamined||0)});
    } catch(e) {}
}
colls.forEach(function(c) {
    var count=db[c].estimatedDocumentCount(); if (count<10) return;
    var sample=db[c].findOne(); if (!sample) return;
    var indexedFields={}; db[c].getIndexes().forEach(function(ix){var k=Object.keys(ix.key||{}); if(k.length)indexedFields[k[0]]=true;});
    Object.keys(sample).filter(function(k){return k!=="_id";}).forEach(function(field){
        var val=sample[field];
        if (typeof val==="string" && val.length<100) testQuery(c,field,"find {"+field+":\"...\"}", JSON.parse("{\""+field+"\":\""+val+"\"}"), indexedFields);
        else if (typeof val==="number") testQuery(c,field,"find {"+field+":{$gt:...}}", JSON.parse("{\""+field+"\":{\"$gt\":"+(val/2)+"}}"), indexedFields);
        else if (typeof val==="boolean") testQuery(c,field,"find {"+field+":"+val+"}", JSON.parse("{\""+field+"\":"+val+"}"), indexedFields);
    });
});

// --- query timing (report anything >50ms) ---
function timeQuery(coll,label,fn){ var s=Date.now(); var n=0; try{n=fn();}catch(e){n=-1;} var ms=Date.now()-s; if(ms>50) out.slow_queries.push({collection:coll, query:label, ms:ms, results:n}); }
colls.forEach(function(c){
    var count=db[c].estimatedDocumentCount(); if (count<100) return;
    var sample=db[c].findOne(); if (!sample) return;
    timeQuery(c,"countDocuments()",function(){return db[c].countDocuments();});
    var sf=Object.keys(sample).filter(function(k){return k!=="_id";}).find(function(f){return typeof sample[f]==="string"&&sample[f].length<50;});
    if (sf){ var v=sample[sf];
        timeQuery(c,"find({"+sf+":...})",function(){return db[c].find(JSON.parse("{\""+sf+"\":\""+v+"\"}")).count();});
        timeQuery(c,"aggregate $group by "+sf,function(){return db[c].aggregate([{$group:{_id:"$"+sf,n:{$sum:1}}}]).toArray().length;});
    }
});

out.summary = { collections: out.collections.length, index_health_findings: out.index_health.length,
                collscan_patterns: out.collscans.length, slow_queries: out.slow_queries.length };
print("MONGOJSON " + JSON.stringify(out));
JS

    # PG-layer findings via PostgreSQL's own JSON builders (single line output).
    PG_SQL="SELECT json_build_object(
      'config', COALESCE((SELECT json_agg(json_build_object('name',name,'setting',setting,'unit',COALESCE(unit,''),'source',source,'default',boot_val) ORDER BY name)
                 FROM pg_settings WHERE name IN ('shared_buffers','effective_cache_size','work_mem','maintenance_work_mem','max_connections','max_wal_size','wal_level')), '[]'::json),
      'cache_top', COALESCE((SELECT json_agg(r) FROM (
                 SELECT COALESCE(c.database_name||'.'||c.collection_name, s.relname) AS collection, s.heap_blks_read AS heap_disk_reads,
                        round(100.0*s.heap_blks_hit/NULLIF(s.heap_blks_read+s.heap_blks_hit,0),2) AS heap_hit_pct,
                        round(100.0*s.idx_blks_hit/NULLIF(s.idx_blks_read+s.idx_blks_hit,0),2) AS idx_hit_pct
                 FROM pg_statio_user_tables s LEFT JOIN documentdb_api_catalog.collections c ON s.relname='documents_'||c.collection_id
                 WHERE s.schemaname='documentdb_data' AND s.relname LIKE 'documents_%' AND (s.heap_blks_read+s.heap_blks_hit)>0
                 ORDER BY s.heap_blks_read DESC LIMIT 5) r), '[]'::json),
      'scan_mix', COALESCE((SELECT json_agg(r) FROM (
                 SELECT COALESCE(c.database_name||'.'||c.collection_name, s.relname) AS collection, s.seq_scan, s.idx_scan,
                        CASE WHEN s.seq_scan+s.idx_scan>0 THEN round(100.0*s.idx_scan/(s.seq_scan+s.idx_scan),1) ELSE 0 END AS idx_scan_pct
                 FROM pg_stat_user_tables s LEFT JOIN documentdb_api_catalog.collections c ON s.relname='documents_'||c.collection_id
                 WHERE s.schemaname='documentdb_data' AND s.relname LIKE 'documents_%' AND s.seq_scan+s.idx_scan>0
                 ORDER BY s.seq_tup_read DESC LIMIT 5) r), '[]'::json),
      'unused_pg_indexes', (SELECT count(*) FROM pg_stat_user_indexes WHERE schemaname='documentdb_data' AND idx_scan=0 AND relname LIKE 'documents_%'),
      'blocked_queries', (SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock')
    );"
    PG_JSON=$(run_psql_raw "$PG_SQL" | grep -vE '^SET$' | tr -d '\n')
    [[ -z "$PG_JSON" ]] && PG_JSON='null'

    MONGO_ARR=""
    first=1
    for CURRENT_DB in $DATABASES; do
        mj=$(run_mongosh "$MONGO_JSON_JS" "$CURRENT_DB" | sed -n 's/^MONGOJSON //p')
        [[ -z "$mj" ]] && continue
        [[ $first -eq 0 ]] && MONGO_ARR+=","
        first=0
        MONGO_ARR+="$mj"
    done

    dbs_json=$(printf '%s' "$DATABASES" | awk '{printf (NR>1?",":"") "\"" $0 "\""}')
    printf '{"databases":[%s],"mongo":[%s],"pg":%s}\n' "$dbs_json" "$MONGO_ARR" "$PG_JSON"
    exit 0
fi


# ══════════════════════════════════════════════════════════════════════
#  LAYER 1: MongoDB API Layer
# ══════════════════════════════════════════════════════════════════════
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  LAYER 1: MongoDB API Diagnostics"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

for CURRENT_DB in $DATABASES; do
echo "┌──────────────────────────────────────────────────────────────┐"
echo "│  Database: $CURRENT_DB"
echo "└──────────────────────────────────────────────────────────────┘"
echo ""

# ── CHECK 1: Database Overview ────────────────────────────────────────
echo "══ CHECK 1: Database & Collection Overview ════════════════════"
echo ""
run_mongosh '
var colls = db.getCollectionNames().sort();
if (colls.length === 0) { print("  (no collections)"); }
else {
    var fmt = function(s,w) { s=String(s); while(s.length<w) s=" "+s; return s; };
    var fmtL = function(s,w) { s=String(s); while(s.length<w) s+=" "; return s; };
    print("  " + fmtL("Collection",25) + fmt("Docs",10) + fmt("AvgSize",10) + fmt("DataSize",12) + fmt("Indexes",10) + fmt("IdxSize",12));
    print("  " + "-".repeat(79));
    var totalDocs = 0, totalSize = 0, totalIdxSize = 0, findings = [];
    colls.forEach(function(c) {
        try {
            var st = db.runCommand({collStats: c});
            var cnt = st.count || 0;
            var avg = st.avgObjSize || 0;
            var size = st.size || 0;
            var nidx = st.nindexes || 0;
            var idxSize = st.totalIndexSize || 0;
            totalDocs += cnt; totalSize += size; totalIdxSize += idxSize;
            var sizeStr = size > 1048576 ? (size/1048576).toFixed(1)+"MB" : size > 1024 ? (size/1024).toFixed(1)+"KB" : size+"B";
            var idxStr = idxSize > 1048576 ? (idxSize/1048576).toFixed(1)+"MB" : idxSize > 1024 ? (idxSize/1024).toFixed(1)+"KB" : idxSize+"B";
            print("  " + fmtL(c,25) + fmt(cnt,10) + fmt(avg+"B",10) + fmt(sizeStr,12) + fmt(nidx,10) + fmt(idxStr,12));
            if (nidx > 15) findings.push("⚠️  " + c + ": " + nidx + " indexes (>15) — write amplification risk");
            if (cnt > 1000 && idxSize > size * 2) findings.push("⚠️  " + c + ": index size exceeds 2x data size");
        } catch(e) {}
    });
    print("  " + "-".repeat(79));
    var tSize = totalSize > 1048576 ? (totalSize/1048576).toFixed(1)+"MB" : (totalSize/1024).toFixed(1)+"KB";
    var tIdx = totalIdxSize > 1048576 ? (totalIdxSize/1048576).toFixed(1)+"MB" : (totalIdxSize/1024).toFixed(1)+"KB";
    print("  " + fmtL("TOTAL",25) + fmt(totalDocs,10) + fmt("",10) + fmt(tSize,12) + fmt("",10) + fmt(tIdx,12));
    if (findings.length > 0) { print(""); findings.forEach(function(f) { print("  " + f); }); }
}
' "$CURRENT_DB"
echo ""

# ── CHECK 2: Index Health ────────────────────────────────────────────
echo "══ CHECK 2: Index Health Analysis ═════════════════════════════"
echo ""
run_mongosh '
var colls = db.getCollectionNames().sort();
var totalFindings = 0;
colls.forEach(function(c) {
    var indexes = db[c].getIndexes();
    if (indexes.length <= 1) return;
    print("  ── " + c + " (" + indexes.length + " indexes) ──");

    // Unused indexes
    try {
        var stats = db[c].aggregate([{$indexStats:{}}]).toArray();
        stats.forEach(function(s) {
            if (s.name === "_id_") return;
            var ops = s.accesses ? Number(s.accesses.ops) : 0;
            if (ops === 0) {
                print("    ⚠️  UNUSED: " + s.name + " — 0 ops since server start");
                totalFindings++;
            }
        });
    } catch(e) {}

    // Redundant (prefix) indexes
    var keyStrings = indexes.map(function(idx) {
        return { name: idx.name, keys: Object.keys(idx.key), keyStr: JSON.stringify(idx.key) };
    });
    for (var i = 0; i < keyStrings.length; i++) {
        for (var j = i+1; j < keyStrings.length; j++) {
            var a = keyStrings[i], b = keyStrings[j];
            if (a.name === "_id_" || b.name === "_id_") continue;
            if (b.keys.length > a.keys.length) {
                var isPrefix = a.keys.every(function(k,idx) { return k === b.keys[idx]; });
                if (isPrefix) {
                    print("    ⚠️  REDUNDANT: " + a.name + " is prefix of " + b.name);
                    totalFindings++;
                }
            }
        }
    }
    print("");
});
if (totalFindings === 0) print("  ✅ No index health issues found");
else print("  Total findings: " + totalFindings);
' "$CURRENT_DB"
echo ""

# ── CHECK 3: COLLSCAN Audit ─────────────────────────────────────────
echo "══ CHECK 3: Collection Scan Audit (auto-discovered) ══════════"
echo ""
run_mongosh '
var findings = [];

// Walk a winning plan to find the index that actually drives it.
// Returns "__COLLSCAN__" for a literal collection scan, the index name for an
// IXSCAN, or null. On DocumentDB an unindexed filter resolves to the _id_ index.
function effectiveIndex(node) {
    var guard = 0;
    while (node && guard++ < 50) {
        if (node.stage === "COLLSCAN") return "__COLLSCAN__";
        if (node.stage === "IXSCAN") return node.indexName || "?";
        node = node.inputStage || (node.inputStages ? node.inputStages[0] : null);
    }
    return null;
}

function testQuery(coll, field, label, filter, sort, indexedFields) {
    var cmd = {find: coll, filter: filter, limit: 1};
    if (sort) cmd.sort = sort;
    try {
        var plan = db.runCommand({explain: cmd, verbosity: "executionStats"});
        var wp = (plan.queryPlanner || {}).winningPlan || {};
        var es = plan.executionStats || {};
        // DocumentDB (Postgres-backed) never emits a literal COLLSCAN stage for
        // an unindexed filter — it falls back to a full IXSCAN over the _id_
        // primary key. Treat either as a full scan. Only report it as a MISSING
        // INDEX when no index actually covers the filtered field (a small
        // collection may resolve to _id_ even when an index exists, because the
        // cost optimizer prefers the PK scan — that is not a missing index).
        var idx = effectiveIndex(wp);
        var fullScan = (idx === "__COLLSCAN__" || idx === "_id_");
        if (fullScan && !(indexedFields && indexedFields[field])) {
            var docsEx = Number(es.totalDocsExamined || 0);
            print("    ⚠️  COLLSCAN: " + coll + " — " + label + " (" + docsEx + " docs scanned)");
            findings.push({c: coll, q: label, docs: docsEx});
        }
    } catch(e) {}
}

function testAgg(coll, label, pipeline) {
    try {
        var plan = db[coll].aggregate(pipeline).explain("executionStats");
        var cursor = (plan.stages && plan.stages[0]) ? plan.stages[0]["$cursor"] : null;
        if (cursor && (cursor.queryPlanner||{}).winningPlan && (cursor.queryPlanner.winningPlan).stage === "COLLSCAN") {
            var docsEx = Number((cursor.executionStats||{}).totalDocsExamined || 0);
            print("    ⚠️  COLLSCAN: " + coll + " — " + label + " (" + docsEx + " docs scanned)");
            findings.push({c: coll, q: label, docs: docsEx});
        }
    } catch(e) {}
}

// Auto-discover collections and test common patterns
var colls = db.getCollectionNames().sort();
colls.forEach(function(c) {
    var count = db[c].estimatedDocumentCount();
    if (count < 10) return; // skip tiny collections
    print("  Testing " + c + " (" + count + " docs)...");

    // Sample a document to discover fields
    var sample = db[c].findOne();
    if (!sample) return;
    var fields = Object.keys(sample).filter(function(k) { return k !== "_id"; });

    // Build the set of fields that lead an existing index (first key). A query
    // on such a field has a usable index even if the planner skips it on small
    // data, so it is NOT a missing index.
    var indexedFields = {};
    db[c].getIndexes().forEach(function(ix) {
        var keys = Object.keys(ix.key || {});
        if (keys.length) indexedFields[keys[0]] = true;
    });

    // Test equality/range filter on each top-level string/number field
    fields.forEach(function(field) {
        var val = sample[field];
        if (typeof val === "string" && val.length < 100) {
            testQuery(c, field, "find {" + field + ":\"...\"}", JSON.parse("{\"" + field + "\":\"" + val + "\"}"), null, indexedFields);
        } else if (typeof val === "number") {
            testQuery(c, field, "find {" + field + ":{$gt:...}}", JSON.parse("{\"" + field + "\":{\"$gt\":" + (val/2) + "}}"), null, indexedFields);
        } else if (typeof val === "boolean") {
            testQuery(c, field, "find {" + field + ":" + val + "}", JSON.parse("{\"" + field + "\":" + val + "}"), null, indexedFields);
        }
    });
    // NOTE: a full-collection $group aggregation always scans every document by
    // design — that is not a missing-index signal, so it is intentionally not
    // flagged here. See CHECK 4 for aggregation timing.
});

print("");
if (findings.length === 0) print("  ✅ No collection scans detected");
else {
    print("  COLLSCAN total: " + findings.length + " query patterns need indexes");
}
' "$CURRENT_DB"
echo ""

# ── CHECK 4: Query Timing ───────────────────────────────────────────
echo "══ CHECK 4: Query Performance Profiling ══════════════════════="
echo ""
run_mongosh '
var results = [];

function timeQuery(coll, label, fn) {
    var start = Date.now();
    var count = 0;
    try { count = fn(); } catch(e) { count = -1; }
    var ms = Date.now() - start;
    var flag = ms > 200 ? " ⚠️ SLOW" : ms > 50 ? " ⚡" : "";
    print("    " + ms + "ms\t" + count + " results\t" + label + flag);
    results.push({ms: ms, label: label, coll: coll});
}

var colls = db.getCollectionNames().sort();
colls.forEach(function(c) {
    var count = db[c].estimatedDocumentCount();
    if (count < 100) return;
    print("  ── " + c + " (" + count + " docs) ──");

    // Sample to get realistic filter values
    var sample = db[c].findOne();
    if (!sample) return;

    // Test count (full scan baseline)
    timeQuery(c, "countDocuments()", function() { return db[c].countDocuments(); });

    // Test filtered find on first string field
    var fields = Object.keys(sample).filter(function(k){return k!=="_id";});
    var strField = fields.find(function(f) { return typeof sample[f] === "string" && sample[f].length < 50; });
    if (strField) {
        var val = sample[strField];
        timeQuery(c, "find({" + strField + ":\"" + val.substring(0,20) + "...\"})", function() {
            return db[c].find(JSON.parse("{\"" + strField + "\":\"" + val + "\"}")).count();
        });
    }

    // Test aggregation
    if (strField) {
        timeQuery(c, "aggregate $group by " + strField, function() {
            return db[c].aggregate([{$group:{_id:"$"+strField, n:{$sum:1}}}]).toArray().length;
        });
    }
    print("");
});

var slow = results.filter(function(r){return r.ms>200;}).length;
var moderate = results.filter(function(r){return r.ms>50&&r.ms<=200;}).length;
var fast = results.length - slow - moderate;
print("  Summary: " + slow + " slow (>200ms), " + moderate + " moderate (50-200ms), " + fast + " fast (<50ms)");
' "$CURRENT_DB"
echo ""

done  # end per-database loop

# ══════════════════════════════════════════════════════════════════════
#  LAYER 2: PostgreSQL Engine Layer
# ══════════════════════════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  LAYER 2: PostgreSQL Engine Diagnostics"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── CHECK 5: Collection-to-PG Table Mapping ──────────────────────────
echo "══ CHECK 5: Collection ↔ PG Table Mapping ════════════════════"
echo ""
run_psql_pretty "
SELECT c.collection_id AS id, c.database_name AS db, c.collection_name AS collection,
       'documents_' || c.collection_id AS pg_table
FROM documentdb_api_catalog.collections c
ORDER BY c.database_name, c.collection_name;
"
echo ""

# ── CHECK 6: PG Table I/O — Sequential vs Index Scans ───────────────
echo "══ CHECK 6: PG Table I/O (Sequential vs Index Scans) ═════════"
echo ""
echo "  Sequential vs index scan counts per table (measured since stats reset):"
echo ""
run_psql_pretty "
SELECT s.relname AS pg_table,
       c.database_name || '.' || c.collection_name AS collection,
       s.seq_scan,
       s.seq_tup_read AS seq_rows_read,
       s.idx_scan,
       s.idx_tup_fetch AS idx_rows_fetched,
       s.n_live_tup AS live_rows,
       CASE WHEN s.seq_scan + s.idx_scan > 0
            THEN round(100.0 * s.idx_scan / (s.seq_scan + s.idx_scan), 1)
            ELSE 0 END AS idx_scan_pct
FROM pg_stat_user_tables s
LEFT JOIN documentdb_api_catalog.collections c
  ON s.relname = 'documents_' || c.collection_id
WHERE s.schemaname = 'documentdb_data'
  AND s.relname LIKE 'documents_%'
  AND s.seq_scan + s.idx_scan > 0
ORDER BY s.seq_tup_read DESC
LIMIT 20;
"
echo ""
echo "  (idx_scan_pct = measured share of scans served by an index. Low values can"
echo "   be normal for small or append-only tables; cross-check with CHECK 3.)"
echo ""

# ── CHECK 7: PG Buffer Cache Hit Rates ──────────────────────────────
echo "══ CHECK 7: Buffer Cache Hit Rates (per collection) ══════════"
echo ""
run_psql_pretty "
SELECT s.relname AS pg_table,
       c.database_name || '.' || c.collection_name AS collection,
       s.heap_blks_read AS heap_disk_reads,
       s.heap_blks_hit AS heap_cache_hits,
       CASE WHEN s.heap_blks_read + s.heap_blks_hit > 0
            THEN round(100.0 * s.heap_blks_hit / (s.heap_blks_read + s.heap_blks_hit), 2)
            ELSE 100 END AS heap_hit_pct,
       s.idx_blks_read AS idx_disk_reads,
       s.idx_blks_hit AS idx_cache_hits,
       CASE WHEN s.idx_blks_read + s.idx_blks_hit > 0
            THEN round(100.0 * s.idx_blks_hit / (s.idx_blks_read + s.idx_blks_hit), 2)
            ELSE 100 END AS idx_hit_pct
FROM pg_statio_user_tables s
LEFT JOIN documentdb_api_catalog.collections c
  ON s.relname = 'documents_' || c.collection_id
WHERE s.schemaname = 'documentdb_data'
  AND s.relname LIKE 'documents_%'
  AND (s.heap_blks_read + s.heap_blks_hit) > 0
ORDER BY s.heap_blks_read DESC
LIMIT 20;
"
echo ""
echo "  (hit_pct = measured share of block reads served from cache since stats reset.)"
echo ""

# ── CHECK 8: PG Index Efficiency ────────────────────────────────────
echo "══ CHECK 8: PG Index Efficiency ══════════════════════════════="
echo ""
echo "  PG indexes with zero scans (potentially unused at engine level):"
echo ""
run_psql_pretty "
SELECT s.relname AS pg_table,
       s.indexrelname AS pg_index,
       s.idx_scan AS scans,
       pg_size_pretty(pg_relation_size(s.indexrelid)) AS index_size
FROM pg_stat_user_indexes s
WHERE s.schemaname = 'documentdb_data'
  AND s.idx_scan = 0
  AND s.relname LIKE 'documents_%'
ORDER BY pg_relation_size(s.indexrelid) DESC
LIMIT 20;
"
echo ""

echo "  PG table + index sizes:"
echo ""
run_psql_pretty "
SELECT s.relname AS pg_table,
       c.database_name || '.' || c.collection_name AS collection,
       pg_size_pretty(pg_relation_size(cl.oid)) AS data_size,
       pg_size_pretty(pg_indexes_size(cl.oid)) AS index_size,
       pg_size_pretty(pg_total_relation_size(cl.oid)) AS total_size,
       CASE WHEN pg_relation_size(cl.oid) > 0
            THEN round(100.0 * pg_indexes_size(cl.oid) / pg_relation_size(cl.oid), 1)
            ELSE 0 END AS idx_data_ratio_pct
FROM pg_class cl
JOIN pg_namespace n ON cl.relnamespace = n.oid
JOIN pg_stat_user_tables s ON s.relid = cl.oid
LEFT JOIN documentdb_api_catalog.collections c
  ON s.relname = 'documents_' || c.collection_id
WHERE n.nspname = 'documentdb_data'
  AND cl.relkind = 'r'
  AND s.relname LIKE 'documents_%'
ORDER BY pg_total_relation_size(cl.oid) DESC
LIMIT 20;
"
echo ""

# ── CHECK 9: PG Connections & Locks ─────────────────────────────────
echo "══ CHECK 9: Connections & Lock Analysis ══════════════════════="
echo ""
echo "  Active connections:"
run_psql_pretty "
SELECT state, count(*) AS count
FROM pg_stat_activity
GROUP BY state
ORDER BY count DESC;
"
echo ""

echo "  Lock summary:"
run_psql_pretty "
SELECT locktype, mode, count(*) AS count
FROM pg_locks
GROUP BY locktype, mode
ORDER BY count DESC
LIMIT 10;
"
echo ""

# Check for blocked queries
BLOCKED=$(run_psql "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock';" | grep -E '^[0-9]+$' | tr -d '[:space:]')
BLOCKED="${BLOCKED:-0}"
if [[ "$BLOCKED" -gt 0 ]] 2>/dev/null; then
    echo "  ⚠️  $BLOCKED queries currently waiting on locks!"
    run_psql_pretty "
    SELECT pid, state, wait_event_type, wait_event,
           now() - query_start AS duration,
           left(query, 80) AS query
    FROM pg_stat_activity
    WHERE wait_event_type = 'Lock'
    LIMIT 5;
    "
else
    echo "  ✅ No blocked queries"
fi
echo ""

# ── CHECK 10: PG Configuration Review ───────────────────────────────
echo "══ CHECK 10: PostgreSQL Configuration Review ═════════════════"
echo ""
echo "  Current settings (FACTUAL — no generic tuning is prescribed; DocumentDB"
echo "  ships tuned defaults and rules-of-thumb are not workload-aware). The"
echo "  'source' and 'default_value' columns show whether a value was changed."
echo ""
run_psql_pretty "
SELECT name, setting, COALESCE(unit, '') AS unit, source, boot_val AS default_value
FROM pg_settings
WHERE name IN (
    'shared_buffers', 'work_mem', 'maintenance_work_mem', 'effective_cache_size',
    'max_connections', 'max_wal_size', 'checkpoint_timeout',
    'random_page_cost', 'seq_page_cost', 'max_worker_processes',
    'max_parallel_workers_per_gather', 'wal_level'
)
ORDER BY name;
"
echo ""

# Check DocumentDB-specific settings
echo "  DocumentDB-specific settings:"
run_psql_pretty "
SELECT name, setting
FROM pg_settings
WHERE name LIKE 'documentdb.%'
ORDER BY name;
"
echo ""

echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  Performance Advisor Complete                                  ║"
echo "║  Layer 1: MongoDB API (collections, indexes, queries)          ║"
echo "║  Layer 2: PostgreSQL Engine (I/O, cache, locks, config)        ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
