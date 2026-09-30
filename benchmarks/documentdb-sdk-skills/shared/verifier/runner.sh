#!/usr/bin/env bash
# Shared verifier runner. Each task's tests/test.sh calls this with the task's
# SDK name as $1.
#
# Responsibilities:
#   1. Start DocumentDB Local (idempotent) and export the generated password.
#   2. Ensure the agent produced /app/build.sh and /app/run.sh.
#   3. Run /app/build.sh.
#   4. Run /app/run.sh in the background.
#   5. Wait for the agent's /health endpoint.
#   6. Run pytest over /verifier/check_*.py + /tests/checks.py.
#   7. Write 0 or 1 to /logs/verifier/reward.txt.
#
# ALWAYS writes reward.txt, defaulting to 0, so an early failure is recorded as
# a failure rather than as a missing file the harness has to interpret.

set -uo pipefail

SDK="${1:-}"
if [ -z "$SDK" ]; then
    echo "[runner] usage: runner.sh <sdk>" >&2
    exit 2
fi
export SDK

LOG_DIR="${VERIFIER_LOG_DIR:-/logs/verifier}"
APP_DIR="${APP_WORKDIR:-/app}"
APP_PORT="${APP_PORT:-9080}"
mkdir -p "$LOG_DIR"
REWARD_FILE="$LOG_DIR/reward.txt"
echo "0" > "$REWARD_FILE"

section() {
    echo
    echo "============================================================"
    echo "[runner] $*"
    echo "============================================================"
}

fail() {
    echo "[runner] FAIL: $*" >&2
    echo "0" > "$REWARD_FILE"
    exit 0   # exit 0: the REWARD is the verdict, not the process exit code
}

# ---------------------------------------------------------------------
section "1. Start DocumentDB"
# ---------------------------------------------------------------------
# The password is generated HERE, in the parent, not inside start-documentdb.
# A child process cannot export a variable back to its caller, and both the
# agent's app and the verifier must end up with the same credential.
# It is generated per container and never baked into the image — check_skills.py
# fails any submission with a hardcoded credential, so the benchmark must not
# model bad practice itself.
if [ -z "${DOCUMENTDB_PASSWORD:-}" ]; then
    DOCUMENTDB_PASSWORD="Bench$(head -c 12 /dev/urandom | od -An -tx1 | tr -d ' \n')"
fi
export DOCUMENTDB_PASSWORD

if ! start-documentdb; then
    fail "DocumentDB did not start. See $LOG_DIR/documentdb.log"
fi

# ---------------------------------------------------------------------
section "2. Check the agent's deliverables"
# ---------------------------------------------------------------------
for f in build.sh run.sh; do
    if [ ! -f "$APP_DIR/$f" ]; then
        fail "$APP_DIR/$f is missing. The task requires both build.sh and run.sh."
    fi
    chmod +x "$APP_DIR/$f" 2>/dev/null || true
done

# ---------------------------------------------------------------------
section "3. Build"
# ---------------------------------------------------------------------
( cd "$APP_DIR" && ./build.sh ) >"$LOG_DIR/build.log" 2>&1
BUILD_RC=$?
if [ $BUILD_RC -ne 0 ]; then
    echo "[runner] build.sh exited $BUILD_RC; last 40 lines:" >&2
    tail -40 "$LOG_DIR/build.log" >&2
    fail "build failed"
fi

# ---------------------------------------------------------------------
section "4. Run"
# ---------------------------------------------------------------------
( cd "$APP_DIR" && ./run.sh ) >"$LOG_DIR/app.log" 2>&1 &
APP_PID=$!

# shellcheck disable=SC2317,SC2329  # invoked indirectly by the EXIT trap below
cleanup() {
    # Stop the agent's app when the verifier exits, however it exits — success,
    # early `fail`, or a timeout. Without this the app keeps holding the port
    # and the database connection after grading finishes.
    if kill -0 "$APP_PID" 2>/dev/null; then
        kill "$APP_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# ---------------------------------------------------------------------
section "5. Wait for /health"
# ---------------------------------------------------------------------
READY=0
for i in $(seq 1 90); do
    if ! kill -0 "$APP_PID" 2>/dev/null; then
        echo "[runner] the app exited during start-up; last 40 lines:" >&2
        tail -40 "$LOG_DIR/app.log" >&2
        fail "app process died before becoming healthy"
    fi
    if curl -fsS "http://localhost:${APP_PORT}/health" >/dev/null 2>&1; then
        echo "[runner] healthy after ${i}s"
        READY=1
        break
    fi
    sleep 1
done
[ "$READY" -eq 1 ] || {
    tail -40 "$LOG_DIR/app.log" >&2
    fail "app did not become healthy on port ${APP_PORT} within 90s"
}

# ---------------------------------------------------------------------
section "6. Grade"
# ---------------------------------------------------------------------
# Prefer the isolated verifier venv so the agent's build.sh cannot shadow a
# verifier dependency (e.g. by installing a different pymongo system-wide).
PY=/opt/verifier-venv/bin/python
[ -x "$PY" ] || PY=python3

# The task's own checks are copied INTO /verifier before running.
#
# pytest only applies a conftest.py to tests at or below its directory, so a
# checks.py sitting in /tests cannot see the shared fixtures in
# /verifier/conftest.py — it fails with "fixture 'sdk' not found". Moving the
# file under /verifier puts it in the same fixture scope as everything else,
# which is also conceptually right: the verifier owns grading.
if [ -f /tests/checks.py ]; then
    cp /tests/checks.py /verifier/task_checks.py
    TASK_CHECKS=/verifier/task_checks.py
else
    TASK_CHECKS=""
    echo "[runner] WARNING: /tests/checks.py not found; task-specific checks skipped" >&2
fi

"$PY" -m pytest \
    --ctrf "$LOG_DIR/ctrf.json" \
    -rA -v \
    -p no:cacheprovider \
    /verifier/check_api.py \
    /verifier/check_behavior.py \
    /verifier/check_documentdb.py \
    /verifier/check_engine.py \
    /verifier/check_source.py \
    /verifier/check_skills.py \
    $TASK_CHECKS \
    2>&1 | tee "$LOG_DIR/pytest.log"

PYTEST_RC=${PIPESTATUS[0]}

# ---------------------------------------------------------------------
section "7. Reward"
# ---------------------------------------------------------------------
if [ "$PYTEST_RC" -eq 0 ]; then
    echo "1" > "$REWARD_FILE"
    echo "[runner] REWARD=1 (all mandatory checks passed)"
else
    echo "0" > "$REWARD_FILE"
    echo "[runner] REWARD=0 (pytest exit $PYTEST_RC)"
fi

# ---------------------------------------------------------------------
section "8. Cost metrics"
# ---------------------------------------------------------------------
# MSBench's reward is binary — it says whether the submission complied, not
# what it cost. Token usage is harvested from the Copilot CLI's own session
# store (which the agent leaves in the container) and written to
# $OUTPUT_DIR/custom_metrics.json, MSBench's first-class per-instance hook.
# This is what lets us compare cost ACROSS tasks later.
#
# Advisory: a failure here must never change the reward. The submission has
# already been graded, and losing cost telemetry is not a grading outcome.
"$PY" /verifier/harvest_metrics.py \
    --ctrf "$LOG_DIR/ctrf.json" \
    --reward "$REWARD_FILE" \
    --output-dir "${OUTPUT_DIR:-/output}" \
    >>"$LOG_DIR/metrics.log" 2>&1 \
    || echo "[runner] WARNING: metric harvest failed; see $LOG_DIR/metrics.log" >&2

# The reward file is the verdict. Exiting non-zero here would make Harbor treat
# a legitimately-failed submission as a broken verifier.
exit 0
