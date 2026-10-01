#!/usr/bin/env python3
"""index-redundancy-render.py — pretty-print index-redundancy-finder findings.

Reads the findings JSON array on stdin (as produced by index-redundancy-finder.sh)
and prints a grouped, severity-sorted human report. Kept as a standalone module
(instead of an inline heredoc in the shell script) so it can be read, linted, and
tested on its own. The shell script pipes findings to it in non-JSON mode.
"""

import json
import sys
from collections import defaultdict
from typing import TextIO

SEV_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
SEV_ICON = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🔵"}


def render(data: list[dict], output: TextIO = sys.stdout):
    if not data:
        print("  ✅ No redundant or unused indexes found", file=output)
        return

    data.sort(key=lambda f: (SEV_ORDER.get(f["severity"], 3), f["collection"], f["rule"]))

    by_coll = defaultdict(list)
    for f in data:
        by_coll[f["collection"]].append(f)

    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in data:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    print(
        f'  Found {len(data)} finding(s): {counts["HIGH"]} HIGH, '
        f'{counts["MEDIUM"]} MEDIUM, {counts["LOW"]} LOW',
        file=output,
    )
    print(file=output)
    for coll in sorted(by_coll):
        print(f"  ── {coll} ──", file=output)
        for f in by_coll[coll]:
            icon = SEV_ICON.get(f["severity"], "  ")
            print(
                f'    {icon} [{f["severity"]}] {f["rule"]:18s} {f["index"]}',
                file=output,
            )
            print(f'         → {f["reason"]}', file=output)
            print(
                f'         💡 db.{coll}.dropIndex("{f["index"]}")',
                file=output,
            )
        print(file=output)


def main():
    render(json.load(sys.stdin))


if __name__ == "__main__":
    main()
