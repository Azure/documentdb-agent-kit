#!/usr/bin/env bash
# run-comparison.sh — measure text-route vs script-route, with a clean context
# for every single run.
#
#   for each iteration:
#     for each arm (ORDER RANDOMISED):
#       fresh database  ->  install exactly one route  ->  fresh agent session
#       ->  grade parity  ->  harvest tokens
#
# WHY EACH RESET IS HERE
# ----------------------
# Every one of these is a leak that would silently favour whichever arm ran
# second, producing a confident and wrong comparison.
#
#   fresh database      $indexStats / idx_scan counters accumulate, and the
#                       redundancy finding depends on them. Running the script
#                       arm first warms those counters and CHANGES THE CORRECT
#                       ANSWER for the text arm. Each run gets its own database
#                       name, seeded from the same deterministic fixture.
#   ANALYZE after seed  stale planner statistics flip query plans; this caused a
#                       real 2-in-7 flake in the deterministic suite.
#   randomised order    prompt-cache warmth is not controllable, so it is
#                       randomised instead — it cannot then systematically
#                       favour one arm across iterations.
#   fresh agent session no conversation history carries between runs, or the
#                       second run answers from the first run's reasoning.
#   arm mutual exclusion install-arm.sh deletes the other route and ASSERTS it
#                       is gone. A leftover file turns one arm into the other.
#   clear /output       a stale finding.json would be graded as this run's answer.
#
# THE AGENT COMMAND
# -----------------
# Set AGENT_CMD to whatever drives your agent non-interactively. The prompt is
# supplied BOTH on stdin and in $PROMPT, so use whichever your agent expects;
# the answer must land at $OUTPUT_DIR/finding.json.
#
# There is deliberately NO default: a silent fallback would emit plausible
# numbers from no agent at all, which is the one outcome worse than no data.
#
# Usage:
#   export DB_PASSWORD=...
#   export AGENT_CMD='copilot --allow-all-tools -p "$PROMPT"'   # prompt as arg
#   #   ... or, for an agent that reads stdin:
#   export AGENT_CMD='my-agent --stdin'
#   bash run-comparison.sh --iterations 5

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT="$(cd "$HERE/../.." && pwd)"
TASK="$HERE/tasks/index-redundancy-diagnosis"
CONTAINER="${DOCDB_CONTAINER:-documentdb-local}"
ITERATIONS=3
OUT_DIR="$HERE/results/raw"
SEED="${RANDOM_SEED:-20260817}"

while [ $# -gt 0 ]; do
    case "$1" in
        --iterations) ITERATIONS="$2"; shift 2;;
        --output-dir) OUT_DIR="$2"; shift 2;;
        *) echo "unknown option: $1" >&2; exit 2;;
    esac
done

if [ -z "${AGENT_CMD:-}" ]; then
    cat >&2 <<'MSG'
AGENT_CMD is not set.

This harness will not invent a fallback. Without a real agent it could only
produce numbers that look like measurements and are not, which is worse than
producing nothing.

  export AGENT_CMD='copilot --allow-all-tools -p "$PROMPT"'

The prompt is supplied both on stdin and in $PROMPT; the answer must be
written to $OUTPUT_DIR/finding.json.
MSG
    exit 2
fi

[ -n "${DB_PASSWORD:-}" ] || { echo "DB_PASSWORD is not set" >&2; exit 2; }
mkdir -p "$OUT_DIR"

MONGO_FLAGS=(-u "${DB_USER:-docdbadmin}" -p "$DB_PASSWORD"
             --authenticationMechanism SCRAM-SHA-256 --tls
             --tlsAllowInvalidCertificates --quiet)

seed_fresh_db() {   # $1 = db name
    local db="$1"
    docker cp "$TASK/fixture.js" "$CONTAINER:/tmp/fx-$db.js" >/dev/null
    docker exec "$CONTAINER" mongosh "localhost:${DOCDB_PORT:-10260}/$db" \
        "${MONGO_FLAGS[@]}" --file "/tmp/fx-$db.js" >/dev/null 2>&1 || return 1
    # Settle planner statistics before anything queries the new database.
    docker exec "$CONTAINER" psql -h localhost -p "${DOCDB_PG_PORT:-9712}" \
        -U "${PG_USER:-documentdb}" -d "${PG_DB:-postgres}" -q -c "ANALYZE" \
        >/dev/null 2>&1 || true
}

drop_db() {
    docker exec "$CONTAINER" mongosh "localhost:${DOCDB_PORT:-10260}/$1" \
        "${MONGO_FLAGS[@]}" --eval 'db.dropDatabase()' >/dev/null 2>&1 || true
}

# Deterministic arm ordering per iteration, from a fixed seed: reproducible,
# but not the same order every time.
arm_order() {   # $1 = iteration
    python3 -c "
import random
r = random.Random($SEED + $1)
arms = ['route-text', 'route-script']
r.shuffle(arms)
print(' '.join(arms))"
}

echo "iterations=$ITERATIONS  seed=$SEED  output=$OUT_DIR"

for i in $(seq 1 "$ITERATIONS"); do
    for arm in $(arm_order "$i"); do
        run_id="iter${i}-${arm}"
        db="route_eval_${i}_${arm//-/_}"
        run_out="$OUT_DIR/$run_id"
        rm -rf "$run_out"; mkdir -p "$run_out"

        echo
        echo "── $run_id  (db=$db) ─────────────────────────────────"

        # 1. fresh database, identical fixture
        drop_db "$db"
        if ! seed_fresh_db "$db"; then
            echo "  seed FAILED; skipping" >&2
            continue
        fi

        # 2. exactly one route on disk, asserted
        if ! KIT_SRC="$KIT" bash "$HERE/shared/arms/install-arm.sh" "$arm" \
                > "$run_out/arm.log" 2>&1; then
            echo "  arm install FAILED — see $run_out/arm.log" >&2
            cat "$run_out/arm.log" >&2
            continue
        fi

        # 3. fresh agent session, identical prompt.
        #
        # The prompt is supplied BOTH on stdin and as $PROMPT, so AGENT_CMD can
        # use whichever its agent expects.
        #
        # This previously assigned a lowercase `prompt` while the command
        # referenced `$PROMPT`, which was never set — so every agent received an
        # EMPTY task, and `|| true` swallowed it. Every run would have failed
        # parity and the conclusion would have been "neither route works".
        # Caught by static analysis (SC2034: `prompt` assigned but never used).
        PROMPT="$(sed "s/__DATABASE__/$db/g" "$TASK/instruction.md")"
        export PROMPT
        if [ -z "$PROMPT" ]; then
            echo "  FATAL: prompt is empty (missing $TASK/instruction.md?)" >&2
            continue
        fi
        OUTPUT_DIR="$run_out" \
        DOCUMENTDB_DATABASE="$db" \
            timeout "${AGENT_TIMEOUT:-900}" \
            bash -c "$AGENT_CMD" <<<"$PROMPT" \
            > "$run_out/agent.log" 2>&1 || true

        # 4. parity FIRST — cost is meaningless without it
        python3 "$HERE/shared/verifier/check_parity.py" \
            --finding "$run_out/finding.json" \
            --expected "$TASK/expected-findings.yaml" \
            --output-dir "$run_out" > "$run_out/parity.log" 2>&1
        parity=$?

        # 5. cost
        python3 "$KIT/benchmarks/documentdb-sdk-skills/shared/verifier/harvest_metrics.py" \
            --output-dir "$run_out" >/dev/null 2>&1 || true

        python3 - "$run_out" "$arm" "$i" "$db" "$parity" <<'PYEOF'
import json, sys, pathlib
run_out, arm, iteration, db, parity_rc = sys.argv[1:6]
d = pathlib.Path(run_out)
metrics = {}
for name in ("custom_metrics.json", "parity.json"):
    p = d / name
    if p.is_file():
        try: metrics.update(json.loads(p.read_text()))
        except Exception: pass
metrics.update({"arm": arm, "iteration": int(iteration), "database": db,
                "parity": parity_rc == "0"})
(d / "run.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
print("  parity=%s  tokens_available=%s  fresh_input=%s" % (
    metrics.get("parity"), metrics.get("tokens_available"),
    metrics.get("tokens_fresh_input")))
PYEOF

        drop_db "$db"
    done
done

echo
echo "raw runs in $OUT_DIR — aggregate with:"
echo "  python3 $HERE/summarize.py $OUT_DIR"
