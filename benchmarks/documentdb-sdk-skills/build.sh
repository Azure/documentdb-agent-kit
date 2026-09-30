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
# Build for the Docker host by default. The published MSBench images remain
# x86_64 (orders.toml); BENCHMARK_PLATFORM=linux/amd64 reproduces those images
# on an ARM host with emulation.
if [ -z "${BENCHMARK_PLATFORM:-}" ]; then
    case "$(docker info --format '{{.Architecture}}')" in
        amd64|x86_64) BENCHMARK_PLATFORM="linux/amd64" ;;
        arm64|aarch64) BENCHMARK_PLATFORM="linux/arm64" ;;
        *) echo "Unsupported Docker host architecture" >&2; exit 1 ;;
    esac
fi
case "$BENCHMARK_PLATFORM" in
    linux/amd64)
        BENCHMARK_ARCH="amd64"
        BASE_DIGEST="2dd1f8875e59b77a679dac82c1b3e7b2179f920db702515f006a82397d9e3b13"
        ;;
    linux/arm64)
        BENCHMARK_ARCH="arm64"
        BASE_DIGEST="325f0149969d583128cc6b773b1d41e191083d8b21bc34d72816b12a4d1c8f61"
        ;;
    *) echo "Unsupported BENCHMARK_PLATFORM: $BENCHMARK_PLATFORM" >&2; exit 1 ;;
esac
# Both child digests are from the pinned DocumentDB image index. A legacy
# Docker builder can otherwise reuse a cached arm64 index for an amd64 build.
BASE_IMAGE="ghcr.io/microsoft/documentdb/documentdb-local@sha256:$BASE_DIGEST"

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
VENDOR_ARCH="$BENCHMARK_ARCH" \
    bash shared/base/vendor-wheels.sh ".wheels/$BENCHMARK_ARCH"

# ---------------------------------------------------------------------------
echo "==> Building base image: $BASE_TAG"
# ---------------------------------------------------------------------------
docker build --platform "$BENCHMARK_PLATFORM" \
    --build-arg "TARGETARCH=$BENCHMARK_ARCH" \
    --build-arg "DOCUMENTDB_BASE_IMAGE=$BASE_IMAGE" \
    -f shared/base/Dockerfile -t "$BASE_TAG" .
BUILT_ARCH="$(docker image inspect "$BASE_TAG" --format '{{.Architecture}}')"
if [ "$BUILT_ARCH" != "$BENCHMARK_ARCH" ]; then
    echo "Base image architecture is $BUILT_ARCH, expected $BENCHMARK_ARCH" >&2
    exit 1
fi

if [ "${1:-}" = "--base-only" ]; then
    echo "==> base image built; stopping (--base-only)"
    exit 0
fi

# ---------------------------------------------------------------------------
echo "==> Building task image: $TASK_TAG"
# ---------------------------------------------------------------------------
# The task image reuses the base's vendored wheels for the reference app's
# dependencies, so it also builds with no network.
cp -r ".wheels/$BENCHMARK_ARCH" tasks/orders-api-python/.wheels
trap 'rm -rf "$HERE/tasks/orders-api-python/.wheels"' EXIT
docker build --platform "$BENCHMARK_PLATFORM" \
    --build-arg "DOCUMENTDB_BENCH_BASE=$BASE_TAG" \
    -f tasks/orders-api-python/environment/Dockerfile \
    -t "$TASK_TAG" tasks/orders-api-python
BUILT_ARCH="$(docker image inspect "$TASK_TAG" --format '{{.Architecture}}')"
if [ "$BUILT_ARCH" != "$BENCHMARK_ARCH" ]; then
    echo "Task image architecture is $BUILT_ARCH, expected $BENCHMARK_ARCH" >&2
    exit 1
fi

echo
echo "Built:"
echo "  $BASE_TAG"
echo "  $TASK_TAG"
echo
echo "Verify both controls:"
echo "  docker run --rm $TASK_TAG bash -c '/solution/solve.sh && /tests/test.sh; cat /logs/verifier/reward.txt'   # must print 1"
echo "  docker run --rm $TASK_TAG bash -c '/tests/test.sh; cat /logs/verifier/reward.txt'                          # must print 0"
