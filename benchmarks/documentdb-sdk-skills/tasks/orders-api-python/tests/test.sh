#!/usr/bin/env bash
# Harbor verifier entrypoint for orders-api-python.
# Delegates to the shared runner, passing the SDK name.
set -uo pipefail

exec /verifier/runner.sh python
