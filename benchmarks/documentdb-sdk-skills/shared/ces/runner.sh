#!/usr/bin/env bash
# runner.sh — agent runner for documentdb-sdk-skills.
#
# THE ORGANIC-DISCOVERY PROTOCOL
# ------------------------------
# This installs the DocumentDB agent kit's skills into the agent's personal
# skills directory as NORMALLY DISCOVERABLE skills, and then drives the default
# agent with NO HINT to use them.
#
# That is the entire point of the benchmark. Telling the agent "use the
# DocumentDB skills" would measure whether a model can follow an instruction —
# an easy question with an uninteresting answer. Not telling it measures
# whether an agent that merely HAS the kit installed actually applies it, which
# is the question a user's experience actually depends on.
#
# ARM SELECTION
# -------------
# SKILLS_ARM=kit      -> install the skills   (benchmark: documentdb-sdk-skills)
# SKILLS_ARM=control  -> install nothing      (benchmark: documentdb-sdk-skills-noskills)
#
# The control arm is a separately registered benchmark, mirroring the
# platform's existing skillsbench / skillsbenchnoskills convention. Only the
# DELTA between the two arms is meaningful.

set -uo pipefail

SKILLS_ARM="${SKILLS_ARM:-kit}"
SKILLS_SRC="${SKILLS_SRC:-/opt/documentdb-agent-kit/skills}"
SKILLS_DEST="${SKILLS_DEST:-$HOME/.copilot/skills}"

echo "[runner] arm=${SKILLS_ARM}"

if [ "$SKILLS_ARM" = "kit" ]; then
    if [ ! -d "$SKILLS_SRC" ]; then
        # Fail loudly. A treatment arm whose skills are missing is silently just
        # a second control arm, and would produce a confident, wrong conclusion
        # that the kit makes no difference.
        echo "[runner] FATAL: SKILLS_ARM=kit but $SKILLS_SRC does not exist." >&2
        exit 1
    fi
    mkdir -p "$SKILLS_DEST"
    cp -r "$SKILLS_SRC"/. "$SKILLS_DEST"/
    echo "[runner] installed $(find "$SKILLS_DEST" -name SKILL.md | wc -l) skills into $SKILLS_DEST"
else
    echo "[runner] control arm: no skills installed"
    # Defensive: make sure a stale layer cannot leak skills into the control.
    rm -rf "$SKILLS_DEST" 2>/dev/null || true
fi

# The prompt is the task statement, verbatim and unaugmented. Nothing here
# mentions DocumentDB best practices, indexes, ESR, connection pooling or the
# skills themselves.
exec "$@"
