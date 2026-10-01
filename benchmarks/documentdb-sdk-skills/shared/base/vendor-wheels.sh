#!/usr/bin/env bash
# vendor-wheels.sh — download the verifier + reference-app wheels on the HOST
# so the image can install them with no network access.
#
# WHY
# ---
# `files.pythonhosted.org` is not reachable from inside Docker's VM on this
# network (blocked by IT policy), although the host itself can reach it. So the
# wheels are resolved once, here, and copied into the build context.
#
# This is not a workaround bolted on: it is how the image SHOULD be built.
# The benchmark promises the agent no internet during grading, and a pinned
# wheel set makes the image reproducible months later when a fresh PyPI
# resolution might not be.
#
# If the public index is blocked on the host too, set PIP_INDEX_URL to an
# approved internal mirror before running, e.g. an Azure Artifacts feed that
# proxies PyPI:
#
#   export PIP_INDEX_URL="https://pkgs.dev.azure.com/<org>/_packaging/<feed>/pypi/simple/"
#
# Usage: bash vendor-wheels.sh [dest-dir]

set -euo pipefail

DEST="${1:-.wheels}"
case "${VENDOR_ARCH:-amd64}" in
    amd64) WHEEL_PLATFORM="manylinux2014_x86_64" ;;
    arm64) WHEEL_PLATFORM="manylinux2014_aarch64" ;;
    *) echo "Unsupported VENDOR_ARCH: $VENDOR_ARCH" >&2; exit 1 ;;
esac

# Pinned, and shared by the base image (verifier) and the task image
# (reference app). One list keeps them from drifting apart.
PACKAGES=(
    "pytest==8.3.3"
    "pytest-json-ctrf==0.3.5"
    "requests==2.32.3"
    "pymongo==4.10.1"
    "psycopg[binary]==3.2.3"
    "pyyaml==6.0.2"
    "fastapi==0.115.4"
    "uvicorn[standard]==0.32.0"
    "pydantic==2.9.2"
    # Backports that only apply to the TARGET interpreter (3.10), listed
    # explicitly because pip evaluates `python_version` environment markers
    # against the interpreter RUNNING the download, not --python-version. On a
    # 3.12 host these silently resolve to "not needed" and the image build then
    # fails with "No matching distribution found for tomli".
    "tomli==2.0.2"
    "exceptiongroup==1.2.2"
)

mkdir -p "$DEST"

# Already vendored? Skip the download — this script runs on every build.
if [ -n "$(ls -A "$DEST" 2>/dev/null || true)" ] && [ -z "${VENDOR_FORCE:-}" ]; then
    echo "    $DEST already populated ($(find "$DEST" -maxdepth 1 -type f | wc -l) files); set VENDOR_FORCE=1 to refresh"
    exit 0
fi

echo "    resolving ${#PACKAGES[@]} pinned packages into $DEST"

# Target the image's interpreter, not the host's: the container is Ubuntu 22.04
# (CPython 3.10). Without these constraints pip would happily
# fetch wheels for the host's Python and they would not import in the image.
PYVER="${VENDOR_PYTHON_VERSION:-310}"

if ! python3 -m pip download \
        --dest "$DEST" \
        --only-binary=:all: \
        --python-version "$PYVER" \
        --implementation cp \
        --abi "cp${PYVER}" \
        --platform "$WHEEL_PLATFORM" \
        "${PACKAGES[@]}" 2>&1 | tail -5; then
    echo
    echo "vendor-wheels: download FAILED." >&2
    echo "  If files.pythonhosted.org is blocked on this host as well, point pip" >&2
    echo "  at an approved internal mirror and re-run:" >&2
    echo "    export PIP_INDEX_URL=<internal pypi mirror>" >&2
    rm -rf "$DEST"
    exit 1
fi

echo "    vendored $(find "$DEST" -maxdepth 1 -type f | wc -l) wheels"
