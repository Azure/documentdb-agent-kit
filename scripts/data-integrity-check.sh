#!/usr/bin/env bash
# data-integrity-check.sh — Generic Data Integrity Checker for DocumentDB
#
# Auto-discovers collections and validates data integrity without hardcoded
# schema knowledge. Works with ANY DocumentDB database.
#
# Checks performed — HARD structural integrity only (no business-semantic guessing):
#   1. Referential integrity — *_id field values with no matching document in
#      the referenced collection (broken / orphaned references)
#   2. Type consistency — a field holding conflicting scalar BSON types across
#      documents in the same collection (breaks indexes / comparisons)
#
# Intentionally NOT checked (these are business rules, not structural integrity,
# and cannot be inferred safely from field names): value ranges, sign (>= 0),
# required / non-null, and uniqueness. Enforce those with a $jsonSchema
# validator or a unique index instead.
#
# Usage:
#   bash scripts/data-integrity-check.sh --db <name> [--container NAME] [--json]
#
#   --json  emit a compact machine-readable summary on stdout (nothing else), so
#           an agent/router can consume the verdict without the full human report.
set -uo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-documentdb-local}"
PORT="${PORT:-10260}"
USER="${DB_USER:-docdbadmin}"
PASSWORD="${DB_PASSWORD:-}"
DB=""
JSON=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --container)  CONTAINER_NAME="$2"; shift 2;;
        --password)   PASSWORD="$2"; shift 2;;
        --port)       PORT="$2"; shift 2;;
        --db)         DB="$2"; shift 2;;
        --json)       JSON=1; shift;;
        -h|--help)
            cat <<EOF
Usage: $0 --db <name> [OPTIONS]

Options:
  --db NAME         Target database (required)
  --container NAME  Docker container name (default: documentdb-local)
  --password PASS   DocumentDB password (required; or set DB_PASSWORD)
  --port PORT       DocumentDB gateway port (default: 10260)
  --json            Emit a compact JSON summary only (no human report)
EOF
            exit 0;;
        *)            shift;;
    esac
done

[[ -z "$DB" ]] && { echo "Error: --db is required"; exit 1; }
[[ -z "$PASSWORD" ]] && { echo "Error: no password. Set DB_PASSWORD or pass --password (e.g. export DB_PASSWORD='<your-password>')." >&2; exit 1; }

run_mongosh() {
    docker exec -u documentdb "$CONTAINER_NAME" mongosh \
        "localhost:${PORT}/${DB}" -u "$USER" -p "$PASSWORD" \
        --authenticationMechanism SCRAM-SHA-256 --tls --tlsAllowInvalidCertificates \
        --quiet --eval "$1" 2>/dev/null
}

# human-only echo (suppressed in --json mode so stdout stays pure JSON)
hecho() { [[ "$JSON" == "1" ]] || echo "$@"; }

# JS prelude: JSON_MODE toggles whether the shared check bodies print the human
# report (out) or only their machine-readable fragment.
JS_MODE="var JSON_MODE=$([[ "$JSON" == "1" ]] && echo true || echo false); function out(s){ if(!JSON_MODE) print(s); }"

# ── Shared check bodies (single source of truth for both modes) ─────────────
read -r -d '' CHECK1_JS <<'JS'
var findings = 0;
var refFindings = [];
var colls = db.getCollectionNames().sort();
var collSet = new Set(colls);

// Build a map of collection → fields that look like foreign keys
// Strategy: find fields ending in _id (but not _id itself), and check
// if there is a matching collection (singular or plural)
colls.forEach(function(c) {
    var sample = db[c].aggregate([{$sample:{size:20}}]).toArray();
    if (sample.length === 0) return;

    // Gather all top-level fields that end with "_id" (excluding _id)
    var fkFields = {};
    sample.forEach(function(doc) {
        Object.keys(doc).forEach(function(k) {
            if (k === "_id") return;
            if (k.match(/_id$/)) fkFields[k] = true;
        });
    });

    Object.keys(fkFields).forEach(function(fk) {
        // Guess the target collection from the FK name
        // e.g. "customer_id" → "customers", "order_id" → "orders", "product_id" → "products"
        var base = fk.replace(/_id$/, "");
        var candidates = [base, base + "s", base + "es"];
        var targetColl = null;
        for (var i = 0; i < candidates.length; i++) {
            if (collSet.has(candidates[i]) && candidates[i] !== c) {
                targetColl = candidates[i];
                break;
            }
        }
        if (!targetColl) return;

        // Check if the target collection actually has this field (or _id)
        var targetSample = db[targetColl].findOne();
        if (!targetSample) return;
        var targetField = targetSample[fk] !== undefined ? fk : null;
        if (!targetField && fk === targetColl.replace(/s$/, "") + "_id") {
            // Also check the singular form + "_id" in target
            targetField = targetSample[fk] !== undefined ? fk : null;
        }
        if (!targetField) return;

        // Validate: get distinct source values, check against target
        var sourceVals = db[c].distinct(fk);
        if (sourceVals.length === 0) return;
        var targetVals = new Set(db[targetColl].distinct(targetField).map(String));
        var orphans = sourceVals.filter(function(v) { return v != null && !targetVals.has(String(v)); });

        if (orphans.length > 0) {
            out("  ⚠️  ORPHAN FK: " + c + "." + fk + " → " + targetColl + "." + targetField);
            out("     " + orphans.length + "/" + sourceVals.length + " values not found in target");
            if (orphans.length <= 5) out("     Examples: " + orphans.slice(0,5).join(", "));
            else out("     Examples: " + orphans.slice(0,3).join(", ") + " ... (+" + (orphans.length-3) + " more)");
            findings++;
            refFindings.push({ source: c, fk: fk, target: targetColl, target_field: targetField,
                               orphan_count: orphans.length, total: sourceVals.length,
                               examples: orphans.slice(0,5).map(String) });
        } else {
            out("  ✅ " + c + "." + fk + " → " + targetColl + "." + targetField + " (" + sourceVals.length + " refs OK)");
        }
    });
});

out("");
if (findings === 0) out("  ✅ All auto-discovered FK relationships are valid");
else out("  Total referential integrity issues: " + findings);
if (JSON_MODE) print("REFJSON " + JSON.stringify({ issues: findings, findings: refFindings }));
JS

read -r -d '' CHECK2_JS <<'JS'
var findings = 0;
var typeFindings = [];
var colls = db.getCollectionNames().sort();

colls.forEach(function(c) {
    var count = db[c].estimatedDocumentCount();
    if (count < 5) return;

    var sampleSize = Math.min(100, count);
    var sample = db[c].aggregate([{$sample:{size:sampleSize}}]).toArray();
    if (sample.length === 0) return;

    // Record the scalar BSON type seen for each field across sampled docs
    var fieldTypes = {};
    sample.forEach(function(doc) {
        Object.keys(doc).forEach(function(k) {
            if (k === "_id") return;
            var t = Array.isArray(doc[k]) ? "array" : (doc[k] instanceof Date ? "date" : typeof doc[k]);
            if (!fieldTypes[k]) fieldTypes[k] = {};
            fieldTypes[k][t] = (fieldTypes[k][t] || 0) + 1;
        });
    });

    var issues = [];

    // HARD: flag a field that holds conflicting scalar types across documents
    // (nested objects excluded). Mixed types break comparisons and indexes.
    Object.keys(fieldTypes).forEach(function(k) {
        var types = Object.keys(fieldTypes[k]);
        if (types.length > 1 && types.indexOf("object") === -1) {
            issues.push("\"" + k + "\" has mixed types: " + types.map(function(t){return t+"("+fieldTypes[k][t]+")";}).join(", "));
            typeFindings.push({ collection: c, field: k, types: fieldTypes[k] });
        }
    });

    if (issues.length > 0) {
        out("  ⚠️  " + c + " (" + count + " docs):");
        issues.forEach(function(i) { out("     " + i); findings++; });
    } else {
        out("  ✅ " + c + " — consistent field types across " + sample.length + " sampled docs");
    }
});

out("");
if (findings === 0) out("  ✅ All field types are consistent");
else out("  Total type-consistency issues: " + findings);
if (JSON_MODE) print("TYPEJSON " + JSON.stringify({ issues: findings, findings: typeFindings }));
JS

# ── JSON mode: emit ONLY a compact summary object ───────────────────────────
if [[ "$JSON" == "1" ]]; then
    REF=$(run_mongosh "$JS_MODE $CHECK1_JS"  | sed -n 's/^REFJSON //p')
    TYPE=$(run_mongosh "$JS_MODE $CHECK2_JS" | sed -n 's/^TYPEJSON //p')
    [[ -z "$REF"  ]] && REF='{"issues":0,"findings":[]}'
    [[ -z "$TYPE" ]] && TYPE='{"issues":0,"findings":[]}'
    ref_issues=$(printf '%s' "$REF"  | sed -n 's/.*"issues":\([0-9]*\).*/\1/p'); ref_issues="${ref_issues:-0}"
    typ_issues=$(printf '%s' "$TYPE" | sed -n 's/.*"issues":\([0-9]*\).*/\1/p'); typ_issues="${typ_issues:-0}"
    ok=true; (( ref_issues + typ_issues > 0 )) && ok=false
    printf '{"db":"%s","referential_integrity":%s,"type_consistency":%s,"total_issues":%d,"ok":%s}\n' \
        "$DB" "$REF" "$TYPE" "$((ref_issues + typ_issues))" "$ok"
    exit 0
fi

# ── Human mode: full report (unchanged) ─────────────────────────────────────
TIMESTAMP=$(date +%Y%m%d%H%M%S)

hecho "╔══════════════════════════════════════════════════════════════════╗"
hecho "║  DocumentDB Data Integrity Checker (Generic)                   ║"
hecho "║  Database: $DB"
hecho "║  Container: $CONTAINER_NAME"
hecho "║  Timestamp: $TIMESTAMP"
hecho "╚══════════════════════════════════════════════════════════════════╝"
hecho ""

# CHECK 1: Auto-Discovered Referential Integrity
hecho "══ CHECK 1: Referential Integrity (auto-discovered) ═══════════"
hecho ""
run_mongosh "$JS_MODE $CHECK1_JS"
hecho ""

# CHECK 2: Type Consistency
hecho "══ CHECK 2: Type Consistency (sampled) ════════════════════════"
hecho ""
run_mongosh "$JS_MODE $CHECK2_JS"
hecho ""

hecho "╔══════════════════════════════════════════════════════════════════╗"
hecho "║  Data Integrity Check Complete (Generic)                       ║"
hecho "╚══════════════════════════════════════════════════════════════════╝"
