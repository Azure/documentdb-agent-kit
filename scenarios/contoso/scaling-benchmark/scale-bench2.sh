#!/usr/bin/env bash
# scale-bench2.sh — kill-tolerant Contoso scaling benchmark.
# Seeding is resumable, so each scale is retried (ensuring the container up
# every attempt) until opportunities == 500*scale, then benched.
set -uo pipefail

SCALES="${1:-1 2 4 6 8 16}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONT="${CONTAINER:-documentdb-local}"
DB_USER="${DB_USER:-docdbadmin}"
PASSWORD="${DB_PASSWORD:-}"
[[ -z "$PASSWORD" ]] && { echo "Error: no password. Set DB_PASSWORD (e.g. export DB_PASSWORD='<your-password>')." >&2; exit 1; }
A=(-u "$DB_USER" -p "$PASSWORD" --authenticationMechanism SCRAM-SHA-256 --tls --tlsAllowInvalidCertificates --quiet)
RESULTS="$DIR/results.tsv"
QREPS="${QREPS:-5}"
MAXTRY="${MAXTRY:-40}"

ensure(){ for i in $(seq 1 120); do docker start "$CONT" >/dev/null 2>&1; docker exec "$CONT" mongosh "localhost:10260/admin" "${A[@]}" --eval "db.runCommand({ping:1}).ok" 2>/dev/null | grep -q 1 && return 0; sleep 1; done; return 1; }
oppcount(){ docker exec "$CONT" mongosh "localhost:10260/$1" "${A[@]}" --eval "print(db.opportunities.countDocuments())" 2>/dev/null | tr -dc '0-9'; }

ensure || { echo "not ready"; exit 1; }
docker cp "$DIR/../contoso-seed.js"    "$CONT:/tmp/contoso-seed.js"    >/dev/null 2>&1
docker cp "$DIR/../contoso-queries.js" "$CONT:/tmp/contoso-queries.js" >/dev/null 2>&1

: > "${RESULTS}.tmp" 2>/dev/null || true
echo -e "scale\topp_count\ttotal_min_ms\tpipeline\tstage\tmonthly\ttopacct\tprodmix\treplead\tavgindustry\theap_bytes\ttoast_bytes" > "$RESULTS"

for S in $SCALES; do
  DB="contoso_x${S}"; EXP=$((500*S))
  echo "── x${S} (${DB}) target opps=${EXP} ──"
  # seed-until-complete
  try=0; cnt=0
  while [[ "$try" -lt "$MAXTRY" ]]; do
    try=$((try+1))
    ensure || { echo "  attempt ${try}: not ready"; continue; }
    cnt=$(oppcount "$DB"); cnt="${cnt:-0}"
    [[ "$cnt" == "$EXP" ]] && { echo "  seeded (${cnt}) after ${try} attempt(s)"; break; }
    echo "  attempt ${try}: have ${cnt}, seeding..."
    docker exec -e CONTOSO_DB="$DB" -e CONTOSO_SCALE="$S" "$CONT" mongosh "localhost:10260/${DB}" "${A[@]}" --file /tmp/contoso-seed.js >/dev/null 2>&1 || true
  done
  cnt=$(oppcount "$DB"); cnt="${cnt:-0}"
  [[ "$cnt" != "$EXP" ]] && { echo "  WARN: ${DB} incomplete (${cnt}/${EXP}); recording anyway"; }

  # bench with retry (need a QSUMMARY line)
  OUT=""; btry=0
  while [[ "$btry" -lt 12 ]]; do
    btry=$((btry+1)); ensure || continue
    OUT=$(docker exec -e CONTOSO_DB="$DB" -e QUERY_REPS="$QREPS" "$CONT" mongosh "localhost:10260/${DB}" "${A[@]}" --file /tmp/contoso-queries.js 2>/dev/null)
    echo "$OUT" | grep -q QSUMMARY && break
  done
  getq(){ echo "$OUT" | awk -v q="$1" '/QRESULT/ && $0 ~ q {n=$0; sub(/.*"ms":/,"",n); sub(/[,}].*/,"",n); print n; exit}'; }
  TOTAL=$(echo "$OUT" | awk '/QSUMMARY/{n=$0; sub(/.*total_min_ms":/,"",n); sub(/[,}].*/,"",n); print n; exit}')
  Q1=$(getq pipeline_by_territory); Q2=$(getq value_by_stage); Q3=$(getq monthly_bookings)
  Q4=$(getq top_accounts); Q5=$(getq product_mix); Q6=$(getq rep_leaderboard); Q7=$(getq avg_deal_by_industry)

  # sizes with retry
  SZ=""; ztry=0
  while [[ "$ztry" -lt 12 ]]; do
    ztry=$((ztry+1)); ensure || continue
    SZ=$(docker exec "$CONT" psql -h localhost -p 9712 -U documentdb -d postgres -t --no-align -F $'\t' -c "
      SELECT pg_relation_size(t.oid), COALESCE(pg_relation_size(NULLIF(t.reltoastrelid,0)),0)
      FROM documentdb_api_catalog.collections c
      JOIN pg_class t ON t.oid=('documentdb_data.documents_'||c.collection_id)::regclass
      WHERE c.database_name='${DB}' AND c.collection_name='opportunities';" 2>/dev/null | grep -vE '^SET$' | head -1)
    [[ -n "$SZ" ]] && break
  done
  HEAP=$(echo "$SZ" | cut -f1); TOAST=$(echo "$SZ" | cut -f2)

  echo -e "${S}\t${cnt}\t${TOTAL}\t${Q1}\t${Q2}\t${Q3}\t${Q4}\t${Q5}\t${Q6}\t${Q7}\t${HEAP}\t${TOAST}" >> "$RESULTS"
  echo "  => opps=${cnt} total_min_ms=${TOTAL} heap=${HEAP} toast=${TOAST}"
done

echo ""; echo "=== ${RESULTS} ==="; cat "$RESULTS"
