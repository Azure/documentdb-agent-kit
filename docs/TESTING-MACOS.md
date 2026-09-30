# Running the tests on a MacBook

Use this guide to hand off a **local, native-architecture** check of the
Diagnostic Regression Suite and the SDK benchmark's grader controls. It works
on Apple Silicon (`arm64`) and Intel (`x86_64`) Macs. On Apple Silicon, **do
not** force `linux/amd64`: AMD64-on-ARM emulation is not supported for this
benchmark. The published MSBench images are x86-64 and must be validated on an
AMD64 machine; local ARM64 controls check the grader, not the published
skills-on/skills-off effectiveness result.

The `apt-get` commands in the benchmark Dockerfile run **inside its Ubuntu
container**, not on macOS. You do not need APT on your laptop.

## 1. Prerequisites and checkout

Install Docker Desktop and start it. Install Git and Python 3.10+ with `pip`
and `venv` (Homebrew's Python is suitable); use the macOS Terminal or another
shell with Bash available. Allow Docker Desktop enough memory and disk space
for a DocumentDB container and two benchmark images.

```bash
# If needed, install Python through Homebrew, then put its unversioned
# python3/pip shims ahead of the system Python for this terminal session:
brew install python@3.12
export PATH="$(brew --prefix python@3.12)/libexec/bin:$PATH"

# If already cloned, use that checkout instead of cloning another copy.
git clone --branch import-cosmos-test-framework --single-branch \
  https://github.com/lionelc/documentdb-agent-kit.git
cd documentdb-agent-kit
git rev-parse HEAD
python3 --version
python3 -m pip --version
docker version
docker info --format '{{.Architecture}}'
```

Check the repository commit matches the commit being tested; report it with
the results. On Apple Silicon the Docker **server** should report `aarch64` or
`arm64`, and on Intel it should report `x86_64` or `amd64`. If it does not,
correct Docker Desktop's configuration before continuing. Do not set
`BENCHMARK_PLATFORM` to a different architecture.

Keep the commands below in the **same terminal session**. Capture logs outside
the repository, and do not share passwords, connection strings, or unredacted
container configuration:

```bash
RESULTS="$HOME/documentdb-mac-test-results-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RESULTS"
printf 'Logs: %s\n' "$RESULTS"
uname -m > "$RESULTS/host-architecture.txt"
docker info --format '{{.Architecture}}' > "$RESULTS/docker-architecture.txt"
git rev-parse HEAD > "$RESULTS/kit-commit.txt"
```

## 2. Container-free checks

`testing/run.sh` creates a virtual environment and installs the Python test
dependencies. These checks do not need the database:

```bash
bash testing/run.sh -q \
  scenarios/benchmark-config scenarios/benchmark-metrics \
  scenarios/evals-config scenarios/route-efficiency \
  > "$RESULTS/static-tests.log" 2>&1
echo "$?" > "$RESULTS/static-tests.exit"
cat "$RESULTS/static-tests.exit"
tail -30 "$RESULTS/static-tests.log"
```

Continue only if the exit code is `0`.
Two benchmark-config tests can skip when no result artifact was committed;
the route-efficiency pricing cross-check can skip when there are not enough
local model-usage rows. These are not database-related skips.

Lint the benchmark shell entrypoints using the same command as CI (install
ShellCheck with Homebrew if it is not already installed):

```bash
command -v shellcheck >/dev/null 2>&1 || brew install shellcheck
find benchmarks -name '*.sh' -type f -exec shellcheck -e SC1091 {} + \
  > "$RESULTS/shellcheck.log" 2>&1
echo "$?" > "$RESULTS/shellcheck.exit"
cat "$RESULTS/shellcheck.exit"
```

## 3. Live Diagnostic Regression Suite

Use a fresh `documentdb-local` container; if that name already exists, do not
overwrite it without checking whose data it holds. This example uses the
repository's pinned multi-architecture DocumentDB image and generates a
temporary password without printing it:

```bash
export DB_PASSWORD="$(openssl rand -hex 24)"
docker run -d --name documentdb-local \
  -p 10260:10260 -p 9712:9712 \
  -e USERNAME=docdbadmin -e PASSWORD="$DB_PASSWORD" \
  ghcr.io/microsoft/documentdb/documentdb-local@sha256:0fcf634531c1917ad0855ff9f4354aca0a5c5d8e435f08250568deb37eeb0ad5
```

The stock container does not include `mongosh`. Download the **Linux** archive
matching the *container* architecture, verify its pinned digest with macOS's
`shasum`, and copy it into the container:

```bash
case "$(docker image inspect "$(docker inspect documentdb-local --format '{{.Image}}')" --format '{{.Architecture}}')" in
  arm64)
    MONGOSH_ARCH=arm64
    MONGOSH_SHA256=8a30ec1833343985d3d5901bb31cbb9e8e8193200dc08a5bddde343b601b7690
    ;;
  amd64)
    MONGOSH_ARCH=x64
    MONGOSH_SHA256=23edb768189663aaa9732a2340a25b5fc05a314940538809a7840be7f2ce221f
    ;;
  *) echo "Unsupported container architecture" >&2; exit 1 ;;
esac
curl -fsSL "https://downloads.mongodb.com/compass/mongosh-2.3.8-linux-${MONGOSH_ARCH}.tgz" \
  -o "$RESULTS/mongosh.tgz"
printf '%s  %s\n' "$MONGOSH_SHA256" "$RESULTS/mongosh.tgz" | shasum -a 256 -c -
tar xzf "$RESULTS/mongosh.tgz" -C "$RESULTS"
docker cp "$RESULTS/mongosh-2.3.8-linux-${MONGOSH_ARCH}/bin/mongosh" \
  documentdb-local:/usr/local/bin/mongosh
docker cp "$RESULTS/mongosh-2.3.8-linux-${MONGOSH_ARCH}/bin/mongosh_crypt_v1.so" \
  documentdb-local:/usr/local/lib/
docker exec documentdb-local mongosh --version
```

Wait for the gateway to accept connections before running the suite (the first
start may take a while). The loop stops after ten minutes; if it times out,
inspect `docker logs documentdb-local` locally, without sharing credentials:

```bash
READY=0
for ((attempt=0; attempt<120; attempt++)); do
  if docker exec documentdb-local mongosh localhost:10260/admin \
      -u docdbadmin -p "$DB_PASSWORD" --authenticationMechanism SCRAM-SHA-256 \
      --tls --tlsAllowInvalidCertificates --quiet \
      --eval 'db.runCommand({ping:1}).ok' 2>/dev/null | grep -q 1; then
    READY=1
    break
  fi
  sleep 5
done
if [ "$READY" -ne 1 ]; then echo "DocumentDB did not become ready" >&2; exit 1; fi
bash testing/run.sh -q > "$RESULTS/live-regression.log" 2>&1
echo "$?" > "$RESULTS/live-regression.exit"
cat "$RESULTS/live-regression.exit"
tail -40 "$RESULTS/live-regression.log"
```

The live database scenarios must **run**, not skip. If the summary says
`No DB password configured` or `container ... is not running`, fix the
environment and rerun. Previously, 204 tests passed with three non-database
skips on ARM64; counts may change with the branch or local usage history.

## 4. SDK benchmark build and grader controls

These controls create and start their **own** DocumentDB instance inside the
task image; they do not use `documentdb-local` or `DB_PASSWORD`.

```bash
unset BENCHMARK_PLATFORM
( cd benchmarks/documentdb-sdk-skills && bash build.sh ) \
  > "$RESULTS/benchmark-build.log" 2>&1
echo "$?" > "$RESULTS/benchmark-build.exit"
cat "$RESULTS/benchmark-build.exit"
tail -30 "$RESULTS/benchmark-build.log"

# Proceed only when benchmark-build.exit is 0.
( cd benchmarks/documentdb-sdk-skills && \
  bash verify-controls.sh --output "$RESULTS/controls.json" ) \
  > "$RESULTS/benchmark-controls.log" 2>&1
echo "$?" > "$RESULTS/benchmark-controls.exit"
cat "$RESULTS/benchmark-controls.exit"
tail -50 "$RESULTS/benchmark-controls.log"

docker image inspect documentdb-orders-api-python:latest \
  --format '{{.Architecture}}' > "$RESULTS/benchmark-image-architecture.txt"
cat "$RESULTS/benchmark-image-architecture.txt"
```

Expect the image architecture to match the Docker server. The **oracle**
must score reward `1` (previously 31/31 checks); the **empty** submission must
score `0`; and the working-but-naive submission must score `0` (previously
20/30). `controls.json` contains the machine-readable control results. If
the build fails, do not treat the controls as a valid test of this checkout.

## Optional: cross-model configuration checks

These are static configuration checks and dry-run plans, **not** real model
evaluations. If you have Node.js 22+ and npm 11.11.1+ (for example
Homebrew's Node.js 24), run:

```bash
brew install node@24
export PATH="$(brew --prefix node@24)/bin:$PATH"
node --version
npm --version
export VALLY_TELEMETRY_OPTOUT=1 DO_NOT_TRACK=1
( cd evals && npm ci && npm run lint:all && \
  npm run experiment:plan && npm run experiment:quality:plan ) \
  > "$RESULTS/eval-configuration.log" 2>&1
echo "$?" > "$RESULTS/eval-configuration.exit"
tail -30 "$RESULTS/eval-configuration.log"
```

Real evals require authentication, spend AI credits, and are not part of this
free MacBook handoff. The route-efficiency *end-to-end* study requires a real
agent command and replaces the configured skills directory; do not run it
against your personal agent setup. Internal MSBench treatment/control runs
are also outside the scope of this local test.

## Handoff

Send the commit and architecture files, the `.exit` files and summary lines
from the static and live tests, and the benchmark build/control logs and
`controls.json` (plus optional eval config results). Review logs before
sharing them; **never include**
`DB_PASSWORD`, `docker inspect` environment output, or private credentials.
Note any skips and whether they were database-related. For further suites and
the distinction between local controls and real model-based evaluation, see
[the general testing guide](TESTING.md). When finished, stop and remove only
the `documentdb-local` container you created; `unset DB_PASSWORD` in your
terminal.
