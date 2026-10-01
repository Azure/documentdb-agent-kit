#!/usr/bin/env python3
"""Parity grader — did this run reach the correct finding?

Graded FIRST, and it gates the cost comparison. A route that is cheaper because
it answers worse has saved nothing, and reporting its token count as a saving
would be actively misleading.

Parity is checked STRUCTURALLY. The correct answer here is a fact about the
database — which indexes are redundant — so it is exactly checkable, and an LLM
judge would add cost and variance for no gain.

Three ways to fail, deliberately:

  MISSED           a redundant index was not reported
  FALSE POSITIVE   a healthy index was reported as redundant
  UNJUSTIFIED      the right names, but no stated mechanism

The false-positive gate matters as much as the missed-finding one: without it an
arm could "win" parity by naming every index in the database, which is not
correctness.

Usage:
  python3 check_parity.py --finding /output/finding.json \
      --expected /tests/expected-findings.yaml --output-dir /output
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def _load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ImportError:  # pragma: no cover - the image installs pyyaml
        raise SystemExit("pyyaml is required")
    return yaml.safe_load(path.read_text())


def _normalise(names) -> set[str]:
    """Index names, lowercased and stripped.

    Agents legitimately write `accounts.tenant_id_1` or `{tenant_id: 1}`; the
    finding is the same one either way, and failing parity over formatting
    would measure prose, not correctness.
    """
    out = set()
    for raw in names or []:
        n = str(raw).strip().lower()
        n = n.split(".")[-1]                    # accounts.tenant_id_1 -> tenant_id_1
        n = n.strip("`'\" ")
        if n:
            out.add(n)
    return out


def grade(finding: dict, expected: dict) -> dict:
    reported = _normalise(finding.get("redundant_indexes"))
    want = _normalise(expected["redundant_indexes"])
    forbidden = _normalise(expected.get("must_not_report"))

    missed = sorted(want - reported)
    false_positives = sorted(reported & forbidden)
    # Anything reported that is neither expected nor explicitly forbidden is
    # still wrong — it is an index that is not redundant.
    unexpected = sorted(reported - want - forbidden)

    # Justification: the reasoning must name the mechanism, so a lucky guess at
    # the names does not pass as understanding.
    reason_text = " ".join(
        str(v) for v in (
            [finding.get("reason", "")]
            + list(finding.get("reasons", {}).values() if isinstance(
                finding.get("reasons"), dict) else [])
        )
    ).lower()
    unjustified = []
    for index, keywords in (expected.get("reason_keywords") or {}).items():
        if _normalise([index]) & reported:
            if not any(re.search(re.escape(k.lower()), reason_text) for k in keywords):
                unjustified.append(index)

    passed = not (missed or false_positives or unexpected or unjustified)
    return {
        "parity": passed,
        "reported": sorted(reported),
        "expected": sorted(want),
        "missed": missed,
        "false_positives": false_positives,
        "unexpected": unexpected,
        "unjustified": sorted(unjustified),
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--finding", type=Path, required=True)
    p.add_argument("--expected", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, default=Path("/output"))
    args = p.parse_args(argv)

    expected = _load_yaml(args.expected)

    if not args.finding.is_file():
        result = {
            "parity": False,
            "error": f"no finding written to {args.finding}",
        }
    else:
        try:
            finding = json.loads(args.finding.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            result = {"parity": False, "error": f"finding is not valid JSON: {exc}"}
        else:
            result = grade(finding, expected)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "parity.json").write_text(json.dumps(result, indent=2,
                                                           sort_keys=True) + "\n")

    print(json.dumps(result, indent=2, sort_keys=True))
    if result["parity"]:
        print("[parity] PASS", file=sys.stderr)
        return 0
    print("[parity] FAIL — cost from this run must NOT be compared", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
