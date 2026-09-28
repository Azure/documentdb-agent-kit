#!/usr/bin/env bash
# build.sh — stage build inputs, then build the benchmark images.
#
# Two things have to be staged before `docker build` can run, and both are the
# same pattern the Cosmos benchmark uses for its skills:
#
# 1. THE SKILLS (`.skills/`)
#    The treatment arm needs the agent kit's skills inside the image. They live
#    in the sibling `skills/` tree, outside this build context, so they are
#    copied in here rather than widening the context to the whole repo.
#
# 2. THE PYTHON WHEELS (`.wheels/`)
#    The image installs its verifier dependencies from a local wheel directory,
#    with no network access at build time. That is deliberate:
#
#      * The benchmark instruction promises the agent no internet during
#        grading. An image that needs PyPI to build does not honour that.
#      * A pinned wheel set makes the image byte-reproducible; resolving from
#        PyPI months later may not be.
#      * Practically: Docker's VM on some hosts cannot complete a TLS handshake
#        with files.pythonhosted.org even when the host can (an MTU/NAT issue),
#        so downloading on the host and copying in is the only reliable path.
#
# Usage:
#   bash build.sh              # base + task images
#   bash build.sh --base-only

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
BASE_TAG="${BASE_TAG:-documentdb-orders-base:latest}"
TASK_TAG="${TASK_TAG:-documentdb-orders-api-python:latest}"
# The benchmark inputs are intentionally x86-64: vendor-wheels.sh downloads
# manylinux x86_64 wheels and the Dockerfile installs the pinned x64 mongosh
# archive. Pin both builds so Docker Desktop uses amd64 emulation on arm64
# hosts instead of combining an arm64 base image with x86-64 dependencies.
BENCHMARK_PLATFORM="linux/amd64"

cd "$HERE"

# ---------------------------------------------------------------------------
echo "==> Staging skills from $REPO/skills"
# ---------------------------------------------------------------------------
rm -rf .skills
mkdir -p .skills
cp -r "$REPO/skills/." .skills/
echo "    staged $(find .skills -name SKILL.md | wc -l) skills"

# ---------------------------------------------------------------------------
echo "==> Vendoring Python wheels"
# ---------------------------------------------------------------------------
bash shared/base/vendor-wheels.sh .wheels

# ---------------------------------------------------------------------------
echo "==> Building base image: $BASE_TAG"
# ---------------------------------------------------------------------------
docker build --platform "$BENCHMARK_PLATFORM" \
    -f shared/base/Dockerfile -t "$BASE_TAG" .

if [ "${1:-}" = "--base-only" ]; then
    echo "==> base image built; stopping (--base-only)"
    exit 0
fi

# ---------------------------------------------------------------------------
echo "==> Building task image: $TASK_TAG"
# ---------------------------------------------------------------------------
# The task image reuses the base's vendored wheels for the reference app's
# dependencies, so it also builds with no network.
cp -r .wheels tasks/orders-api-python/.wheels
trap 'rm -rf "$HERE/tasks/orders-api-python/.wheels"' EXIT
docker build --platform "$BENCHMARK_PLATFORM" \
    -f tasks/orders-api-python/environment/Dockerfile \
    -t "$TASK_TAG" tasks/orders-api-python

echo
echo "Built:"
echo "  $BASE_TAG"
echo "  $TASK_TAG"
echo
echo "Verify both controls:"
echo "  docker run --rm $TASK_TAG bash -c '/solution/solve.sh && /tests/test.sh; cat /logs/verifier/reward.txt'   # must print 1"
echo "  docker run --rm $TASK_TAG bash -c '/tests/test.sh; cat /logs/verifier/reward.txt'                          # must print 0"
