# ARM64 benchmark verification (2026-09-30)

`Tests ran on Linux
`aarch64`, Docker 29.1.3, Python 3.12.3. The local DocumentDB image was
the repository's pinned multi-architecture digest
`sha256:0fcf634531c1917ad0855ff9f4354aca0a5c5d8e435f08250568deb37eeb0ad5`.
The database container and both benchmark images ran **natively as ARM64**.

| Exercise | Result |
|---|---|
| Full live regression suite (`DB_PASSWORD=... bash testing/run.sh -q`) | **204 passed, 3 skipped, 0 failed** of 207 collected. The skips were two checks for historical committed results (none in this branch) and a route-efficiency pricing cross-check needing additional local model-usage rows. Live fixture, determinism, remediation, diagnostic, benchmark-configuration, and cost-accounting tests executed. |
| Native SDK benchmark build (`bash benchmarks/documentdb-sdk-skills/build.sh`) | **Passed**: ARM64 base and task images built; vendored CPython 3.10 aarch64 wheels installed offline, and checksum-verified ARM64 `mongosh` 2.3.8 ran in the base image. |
| SDK grader controls (`bash verify-controls.sh`) | **Passed**: oracle reward **1**, **31/31** checks; empty app reward **0**; working-but-naive app reward **0**, **20/30** checks. The latter passed all 12 API/behavior checks but failed 10 best-practice checks. |
| Benchmark/portable/route-efficiency static tests | **Passed** within the full suite, including architecture wiring and all available route-efficiency parity and cost tests. |
| Benchmark shell lint and syntax (`shellcheck -e SC1091 ...`; `bash -n ...`) | **Passed** for every benchmark `.sh` file. |
| Vally configuration (`npm run lint:all`) | **Passed** for skill-routing and guidance-quality specs with ARM64 Node.js 24.21.0 / npm 11.19.0. |
| Vally experiment plans (`npm run experiment:plan`; `npm run experiment:quality:plan`) | **Both passed**; model/arm plans resolved. These are dry runs, not agent results. |
| Vally mock routing eval (`npm run eval:mock`) | **40%**, exit 1, as documented: mock invokes zero skills, so positive-trigger cases fail. This verifies plumbing only, not skill efficacy. |
| Vally mock quality eval (`npm run eval:quality:mock`) | **0%**, exit 1, as documented: mock cannot run the judge panel. No guidance-quality conclusion follows. |
| AMD64 build under ARM64 QEMU (`BENCHMARK_PLATFORM=linux/amd64 bash build.sh --base-only`) | **Blocked by host emulation**, not by the native build: the AMD64 base and checksum-verified x64 archive resolved correctly, but QEMU 8.2.2 crashed running the base image's `gpgv`; `apt-get update` then reported unavailable Ubuntu keys. This does not validate the AMD64 build on a real x86-64 runner. |

Live suite breakdown (pass / skip):

| Scenario | Pass | Skip |
|---|---:|---:|
| benchmark-config | 38 | 2 |
| benchmark-metrics | 26 | 0 |
| determinism | 13 | 0 |
| ecommerce-advanced-data | 3 | 0 |
| ecommerce-data-integrity | 4 | 0 |
| ecommerce-healthy-indexes | 2 | 0 |
| ecommerce-missing-index | 3 | 0 |
| ecommerce-redundant-indexes | 4 | 0 |
| evals-config | 22 | 0 |
| json-contract | 17 | 0 |
| kb-router | 18 | 0 |
| portable-cli | 10 | 0 |
| remediation-effect | 7 | 0 |
| route-efficiency | 21 | 1 |
| token-accounting | 16 | 0 |
| **Total** | **204** | **3** |

## Changes made

- Local SDK builds now select the Docker host architecture by default and
  support an explicit `BENCHMARK_PLATFORM=linux/amd64` or `linux/arm64`.
  Both base and task builds verify the resulting image architecture.
- Wheel downloads are separated by target architecture; the Dockerfile
  selects matching wheels and the official `mongosh` archive, checking its
  architecture-specific SHA-256. Docker's legacy builder receives explicit
  build arguments, and base images use the architecture-specific children of
  the already-pinned multi-arch image index. This prevents an ARM64 layer
  cached under the index digest from contaminating an AMD64 build.
- Task builds use the base image they just built, including when custom
  image tags are supplied. Control runs select the **built image's** platform
  rather than forcing AMD64. Architecture guards and setup instructions were
  updated accordingly.
- Cross-model evaluation instructions now state Vally's required Node/npm
  versions. The host's original Node 18 could not parse Vally's CLI; using
  the official ARM64 Node 24 distribution resolved that incompatibility.

The MSBench registration, dataset and publication architecture remain
**x86-64**. These local ARM64 controls validate the instrument, not the
published skills-on/skills-off effectiveness delta. A real MSBench run needs
access to its internal registry/feed and paired agent submissions; it was not
run here. The route-efficiency end-to-end comparison also was not run: it
requires a configured real `AGENT_CMD`, consumes agent credits, and its arm
installer deletes the configured skills destination (by default the user's
`~/.copilot/skills`). Neither benchmark has a measured treatment/control
effectiveness result from this exercise.
