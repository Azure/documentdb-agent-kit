#!/usr/bin/env bash
# verify-controls.sh — reproduce every grader-validation number in docs/REPORT.md.
#
# Runs the three control submissions against the built task image and asserts
# the expected reward for each. This is the positive/negative control pair that
# makes the benchmark trustworthy:
#
#   oracle   must score 1  — otherwise the grader cannot be satisfied and every
#                            measured score is meaningless
#   empty    must score 0  — weak, but proves missing deliverables are noticed
#   naive    must score 0  — THE important one: a fully working app with no
#                            DocumentDB best practices must still fail
#
# A grader that cannot fail is worthless; a grader that cannot pass is broken.
# This checks both directions, plus the case in between that actually matters.
#
# Usage:
#   bash build.sh              # once, to build the images
#   bash verify-controls.sh    # ~10 min: each run seeds 20k documents
#   bash verify-controls.sh --only naive

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_DIR="$HERE/tasks/orders-api-python"
IMAGE="${TASK_TAG:-documentdb-orders-api-python:latest}"
BENCHMARK_PLATFORM="linux/amd64"
ONLY=""
RESULT_JSON=""
while [ $# -gt 0 ]; do
    case "$1" in
        --only)   ONLY="${2:-}"; shift 2;;
        --output) RESULT_JSON="${2:-}"; shift 2;;
        *) echo "unknown option: $1" >&2; exit 2;;
    esac
done

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "Image $IMAGE not found. Run:  bash build.sh" >&2
    exit 1
fi

FAILURES=0
RESULTS_TMP="$(mktemp)"
trap 'rm -f "$RESULTS_TMP"' EXIT

# run_control <name> <expected-reward> <setup-command>
run_control() {
    local name="$1" expected="$2" setup="$3"
    if [ -n "$ONLY" ] && [ "$ONLY" != "$name" ]; then return 0; fi

    echo
    echo "══════════════════════════════════════════════════════════════"
    echo "  control: $name   (expect reward=$expected)"
    echo "══════════════════════════════════════════════════════════════"

    local out
    out=$(docker run --rm --platform "$BENCHMARK_PLATFORM" \
        -v "$TASK_DIR/tests:/tests:ro" \
        -v "$TASK_DIR/solution:/solution:ro" \
        -v "$HERE/controls:/controls:ro" \
        "$IMAGE" \
        bash -c "$setup /tests/test.sh >/dev/null 2>&1; \
                 echo \"REWARD=\$(cat /logs/verifier/reward.txt)\"; \
                 python3 -c \"
import json
try:
    d = json.load(open('/output/custom_metrics.json'))
except Exception:
    raise SystemExit
print('CHECKS=%s/%s' % (d.get('checks_passed'), d.get('checks_total')))
for c in ['api','behavior','documentdb','engine','source','skills']:
    p, t = d.get('checks_%s_passed' % c), d.get('checks_%s_total' % c)
    if t: print('  %-12s %s/%s' % (c, p, t))
\"" 2>&1)

    echo "$out"

    local actual checks
    actual=$(echo "$out" | sed -n 's/^REWARD=//p' | tail -1)
    checks=$(echo "$out" | sed -n 's/^CHECKS=//p' | tail -1)
    # Record for the machine-readable artifact. Categories are captured from the
    # container's own custom_metrics.json, not re-derived here, so the committed
    # result cannot drift from what the verifier actually reported.
    printf '%s\t%s\t%s\t%s\n' "$name" "$expected" "$actual" "${checks:-}" >> "$RESULTS_TMP"
    if [ "$actual" = "$expected" ]; then
        echo "  ✅ $name: reward=$actual as expected"
    else
        echo "  ❌ $name: reward=$actual, EXPECTED $expected" >&2
        FAILURES=$((FAILURES + 1))
    fi
}

# The oracle: copies the reference implementation into /app.
run_control oracle 1 '/solution/solve.sh >/dev/null 2>&1 &&'

# Empty: nothing in /app at all.
run_control empty 0 'true &&'

# Naive: functional, but follows no DocumentDB best practice.
run_control naive 0 'mkdir -p /app && cp -r /controls/naive-python/. /app/ && chmod +x /app/*.sh &&'

if [ -n "$RESULT_JSON" ]; then
    mkdir -p "$(dirname "$RESULT_JSON")"
    KIT_COMMIT="$(git -C "$HERE" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    python3 - "$RESULTS_TMP" "$RESULT_JSON" "$KIT_COMMIT" "$IMAGE" <<'PYEOF'
import json, subprocess, sys, datetime
rows_path, out_path, commit, image = sys.argv[1:5]
controls = {}
for line in open(rows_path):
    name, expected, actual, checks = (line.rstrip("\n").split("\t") + ["", "", "", ""])[:4]
    passed = total = None
    if checks and "/" in checks:
        p, t = checks.split("/", 1)
        passed, total = int(p), int(t)
    controls[name] = {
        "expected_reward": int(expected),
        "actual_reward": int(actual) if actual.isdigit() else None,
        "checks_passed": passed,
        "checks_total": total,
        "as_expected": actual == expected,
    }
artifact = {
    "kind": "controls-validation",
    "provenance": {
        "date": datetime.date.today().isoformat(),
        "kit_commit": commit,
        "image_tag": image,
        "host": "local docker",
        "command": "bash verify-controls.sh",
    },
    "controls": controls,
    "all_as_expected": all(c["as_expected"] for c in controls.values()),
}
json.dump(artifact, open(out_path, "w"), indent=2, sort_keys=True)
open(out_path, "a").write("\n")
print(f"  wrote {out_path}")
PYEOF
fi

echo
echo "══════════════════════════════════════════════════════════════"
if [ "$FAILURES" -eq 0 ]; then
    echo "  ✅ all controls behaved as expected"
    exit 0
fi
echo "  ❌ $FAILURES control(s) did not behave as expected" >&2
echo "     The grader is not trustworthy until this is resolved." >&2
exit 1
