#!/usr/bin/env bash
#
# Install the documentdb-agent-kit skills into an agent's skills directory,
# with OPTIONAL, opt-in usage telemetry.
#
# Telemetry is OFF by default. It is only sent when you pass --telemetry or set
# DDBKIT_TELEMETRY=1. When enabled, one anonymous "install" event is sent to
# Azure Application Insights: target agent, list of skill names, kit version,
# and OS family. No file contents, personal data, or machine identifiers beyond
# a random per-invocation id. See TELEMETRY.md.
#
# Usage:
#   ./scripts/install.sh [--target claude-project|claude-user|<path>] [--symlink] [--telemetry]
#
set -euo pipefail

# --- Config -----------------------------------------------------------------
KIT_VERSION="1.0.0"
# App Insights ingestion key. Supply your own via the DDBKIT_AIKEY environment
# variable. An instrumentation key is an ingestion-only identifier; it is kept
# out of source control here so the repo ships without a live endpoint.
INSTRUMENTATION_KEY="${DDBKIT_AIKEY:-<YOUR_APPINSIGHTS_INSTRUMENTATION_KEY>}"
INGESTION_ENDPOINT="https://dc.services.visualstudio.com/v2/track"

TARGET="claude-project"
SYMLINK=0
TELEMETRY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)    TARGET="$2"; shift 2 ;;
    --symlink)   SYMLINK=1; shift ;;
    --telemetry) TELEMETRY=1; shift ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILLS_ROOT="$REPO_ROOT/skills"

if [[ ! -d "$SKILLS_ROOT" ]]; then
  echo "skills/ not found at '$SKILLS_ROOT'. Run this from inside the documentdb-agent-kit repo." >&2
  exit 1
fi

# --- Resolve target directory ----------------------------------------------
case "$TARGET" in
  claude-project) DEST="$REPO_ROOT/.claude/skills" ;;
  claude-user)    DEST="$HOME/.claude/skills" ;;
  *)              DEST="$TARGET" ;;
esac

mkdir -p "$DEST"

# --- Install ----------------------------------------------------------------
installed=()
for dir in "$SKILLS_ROOT"/*/; do
  name="$(basename "$dir")"
  link="$DEST/$name"
  rm -rf "$link"
  if [[ "$SYMLINK" -eq 1 ]]; then
    ln -s "$dir" "$link"
  else
    cp -R "$dir" "$link"
  fi
  installed+=("$name")
done

echo "Installed ${#installed[@]} skills into $DEST"
for s in "${installed[@]}"; do echo "  - $s"; done

# --- Opt-in telemetry -------------------------------------------------------
if [[ "$TELEMETRY" -ne 1 && "${DDBKIT_TELEMETRY:-}" != "1" ]]; then
  echo ""
  echo "Usage telemetry: OFF. Re-run with --telemetry (or set DDBKIT_TELEMETRY=1) to"
  echo "help the maintainers see which skills are installed. See TELEMETRY.md."
  exit 0
fi

case "$INSTRUMENTATION_KEY" in
  "<"*">") echo "" ; echo "Telemetry requested but no App Insights key configured. Set DDBKIT_AIKEY to enable. Skipping." ; exit 0 ;;
esac

if ! command -v curl >/dev/null 2>&1; then
  echo "" ; echo "curl not found; skipping telemetry." ; exit 0
fi

case "$(uname -s)" in
  Linux*)  OS_FAMILY="linux" ;;
  Darwin*) OS_FAMILY="macos" ;;
  MINGW*|MSYS*|CYGWIN*) OS_FAMILY="windows" ;;
  *) OS_FAMILY="unknown" ;;
esac

method=$([[ "$SYMLINK" -eq 1 ]] && echo "symlink" || echo "copy")
skills_csv="$(IFS=,; echo "${installed[*]}")"
now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
invocation_id="$(cat /proc/sys/kernel/random/uuid 2>/dev/null || echo "$RANDOM-$RANDOM-$RANDOM")"

payload=$(cat <<JSON
{
  "name": "Microsoft.ApplicationInsights.Event",
  "time": "$now",
  "iKey": "$INSTRUMENTATION_KEY",
  "tags": { "ai.cloud.role": "documentdb-agent-kit-installer" },
  "data": {
    "baseType": "EventData",
    "baseData": {
      "ver": 2,
      "name": "skill_install",
      "properties": {
        "kitVersion": "$KIT_VERSION",
        "target": "$TARGET",
        "osFamily": "$OS_FAMILY",
        "method": "$method",
        "skills": "$skills_csv",
        "invocationId": "$invocation_id"
      },
      "measurements": { "skillCount": ${#installed[@]} }
    }
  }
}
JSON
)

# Telemetry must never break an install.
if curl -sf -m 10 -X POST "$INGESTION_ENDPOINT" \
     -H "Content-Type: application/json" \
     -d "$payload" >/dev/null 2>&1; then
  echo "" ; echo "Anonymous install event sent. Thank you!"
else
  echo "" ; echo "Telemetry send failed (ignored)."
fi
