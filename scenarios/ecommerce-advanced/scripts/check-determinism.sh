#!/usr/bin/env bash
# Generate the dataset twice in clean directories and require byte-identical
# output. A deterministic fixture that cannot reproduce itself is not a test
# fixture.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
TMP="$ROOT/.tmp"

rm -rf "$TMP"
mkdir -p "$TMP/one" "$TMP/two"
trap 'rm -rf "$TMP"' EXIT

node "$HERE/generate.mjs" --output "$TMP/one" >/dev/null
node "$HERE/generate.mjs" --output "$TMP/two" >/dev/null

diff -ru "$TMP/one" "$TMP/two"
echo "PASS: two clean generations are byte-identical"

