#!/usr/bin/env bash
# install-arm.sh — put exactly ONE route on disk, and prove the other is gone.
#
#   route-text    the kit's text skills;  scripts/ and knowledge-base/ REMOVED
#   route-script  scripts/ + knowledge-base/;  skills/ REMOVED
#
# The arm is expressed purely by what exists on disk. The agent is never told
# which arm it is in, and the task prompt is identical either way — so any
# difference in cost or correctness comes from the route, not from instruction.
#
# WHY THIS SCRIPT ASSERTS RATHER THAN JUST COPYING
# ------------------------------------------------
# A leftover file silently converts one arm into the other, and the run would
# still complete and still report a number. That is the worst failure mode
# available here: it produces a confident comparison of an arm against itself.
# So after installing, this verifies the other route is actually absent and
# fails loudly if it is not.

set -uo pipefail

ARM="${1:-}"
KIT_SRC="${KIT_SRC:-/opt/documentdb-agent-kit}"
SKILLS_DEST="${SKILLS_DEST:-$HOME/.copilot/skills}"
TOOLS_DEST="${TOOLS_DEST:-/opt/documentdb-tools}"

case "$ARM" in
    route-text|route-script) ;;
    *) echo "usage: install-arm.sh {route-text|route-script}" >&2; exit 2;;
esac

echo "[arm] installing $ARM"

# Always start from nothing, so a previous run cannot contribute.
rm -rf "$SKILLS_DEST" "$TOOLS_DEST" 2>/dev/null || true
mkdir -p "$SKILLS_DEST"

case "$ARM" in
route-text)
    if [ ! -d "$KIT_SRC/skills" ]; then
        echo "[arm] FATAL: $KIT_SRC/skills missing — the text arm would be empty," >&2
        echo "[arm]        which silently makes it a no-kit control." >&2
        exit 1
    fi
    cp -r "$KIT_SRC/skills/." "$SKILLS_DEST"/
    echo "[arm] installed $(find "$SKILLS_DEST" -name SKILL.md | wc -l) skills"
    ;;
route-script)
    if [ ! -d "$KIT_SRC/scripts" ] || [ ! -d "$KIT_SRC/knowledge-base" ]; then
        echo "[arm] FATAL: $KIT_SRC/{scripts,knowledge-base} missing — the script" >&2
        echo "[arm]        arm would have no route and would silently fall back" >&2
        echo "[arm]        to reasoning, i.e. become the text arm." >&2
        exit 1
    fi
    mkdir -p "$TOOLS_DEST"
    cp -r "$KIT_SRC/scripts" "$KIT_SRC/knowledge-base" "$TOOLS_DEST"/
    chmod +x "$TOOLS_DEST"/scripts/*.sh "$TOOLS_DEST"/knowledge-base/*.sh 2>/dev/null || true
    echo "[arm] installed $(find "$TOOLS_DEST/scripts" -maxdepth 1 -name '*.sh' 2>/dev/null | wc -l) scripts + router"
    ;;
esac

# ---------------------------------------------------------------------------
# Mutual exclusion. An arm contaminated with the other route is not an arm.
# ---------------------------------------------------------------------------
fail=0
if [ "$ARM" = "route-text" ]; then
    if [ -d "$TOOLS_DEST" ]; then
        echo "[arm] FATAL: $TOOLS_DEST exists in the TEXT arm" >&2; fail=1
    fi
    if [ ! -s "$(find "$SKILLS_DEST" -name SKILL.md | head -1)" ] 2>/dev/null; then
        echo "[arm] FATAL: no SKILL.md installed in the TEXT arm" >&2; fail=1
    fi
else
    if find "$SKILLS_DEST" -name SKILL.md 2>/dev/null | grep -q .; then
        echo "[arm] FATAL: SKILL.md files present in the SCRIPT arm" >&2; fail=1
    fi
    if [ ! -x "$TOOLS_DEST/knowledge-base/kb-route.sh" ]; then
        echo "[arm] FATAL: router not executable in the SCRIPT arm" >&2; fail=1
    fi
fi

if [ "$fail" -ne 0 ]; then
    echo "[arm] the arms are not mutually exclusive; refusing to run." >&2
    exit 1
fi

echo "[arm] $ARM verified: the other route is absent"
