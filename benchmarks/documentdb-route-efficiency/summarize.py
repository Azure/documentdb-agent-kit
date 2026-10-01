#!/usr/bin/env python3
"""Aggregate route-efficiency runs into the comparison table.

THE RULE THIS ENFORCES
----------------------
Cost is compared **only among runs that reached parity**. A route that is
cheaper because it answered wrong has saved nothing, and averaging its tokens in
would manufacture a saving out of a failure. Runs that missed parity are counted
and reported — they are the more interesting result — but excluded from the cost
means.

Usage:
  python3 summarize.py results/raw [--json] [--out results/<date>-route-efficiency.md]
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent / "shared" / "verifier"))
import pricing  # noqa: E402

ARMS = ["route-text", "route-script"]

# USD is the headline. One token of Gemini 3.1 Pro is not one token of GPT-5.6
# Sol — output differs 2.5x and input 2.5x — so a cross-model table in raw
# tokens ranks tokenisers and verbosity rather than cost.
COST_KEYS = [
    ("usd_total", "USD", "${:,.4f}"),
    ("tokens_fresh_input", "Fresh input tokens", "{:,.0f}"),
    ("tokens_output", "Output tokens", "{:,.0f}"),
    ("ai_credits", "AI credits", "{:,.2f}"),
    ("agent_turns", "Turns", "{:,.1f}"),
    ("cache_read_share_pct", "Cache share %", "{:.1f}"),
]


def load_runs(root: Path) -> list[dict]:
    runs = []
    for path in sorted(root.glob("*/run.json")):
        try:
            runs.append(json.loads(path.read_text()))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    return runs


def summarise(runs: list[dict]) -> dict:
    out = {}
    for arm in ARMS:
        mine = [r for r in runs if r.get("arm") == arm]
        parity_ok = [r for r in mine if r.get("parity")]
        # Cost means come from parity-passing runs ONLY.
        costed = [r for r in parity_ok if r.get("tokens_available")
                  or r.get("input_tokens")]

        # Price each run against its OWN model's published rates before
        # averaging; averaging tokens across models and pricing afterwards
        # would charge one model's rate for another's usage.
        for r in costed:
            if "usd_total" not in r and r.get("model"):
                try:
                    r["usd_total"] = pricing.cost_usd(r, r["model"])["usd_total"]
                except pricing.UnknownModel:
                    r["usd_total"] = None

        cost = {}
        for key, _, _ in COST_KEYS:
            vals = [float(r[key]) for r in costed if r.get(key) is not None]
            cost[key] = statistics.mean(vals) if vals else None

        out[arm] = {
            "runs": len(mine),
            "parity_passed": len(parity_ok),
            "parity_rate": (len(parity_ok) / len(mine)) if mine else None,
            "costed_runs": len(costed),
            "missing_token_data": len(parity_ok) - len(costed),
            "cost": cost,
        }
    return out


def render(summary: dict, runs: list[dict]) -> str:
    L, A = [], None
    A = L.append
    A("# Route efficiency — text skills vs diagnostic scripts")
    A("")
    A("")

    A("## Parity — graded first")
    A("")
    A("| Arm | Runs | Reached correct finding | Rate |")
    A("|---|---|---|---|")
    for arm in ARMS:
        s = summary[arm]
        rate = "—" if s["parity_rate"] is None else f"{s['parity_rate']:.0%}"
        A(f"| `{arm}` | {s['runs']} | {s['parity_passed']} | {rate} |")
    A("")

    t, sc = summary["route-text"], summary["route-script"]
    if t["parity_rate"] is not None and sc["parity_rate"] is not None:
        if t["parity_rate"] < sc["parity_rate"]:
            A("> The text route reached the correct finding **less often**. If "
              "that holds up, the headline is about correctness, not tokens — "
              "and a cheaper route that is also more reliable is a stronger "
              "claim than a token saving.")
            A("")
        elif t["parity_rate"] > sc["parity_rate"]:
            A("> ⚠️ The **script** route reached the correct finding less often. "
              "Any token saving it shows is therefore suspect: check whether the "
              "script answers a narrower question than the one asked.")
            A("")

    A("## Cost (parity-passing runs only)")
    A("")
    A("| Metric | text route | script route | Saving |")
    A("|---|---|---|---|")
    for key, label, fmt in COST_KEYS:
        tv, sv = t["cost"].get(key), sc["cost"].get(key)
        if tv is None or sv is None:
            saving = "—"
        elif key == "cache_read_share_pct":
            saving = "n/a"
        elif tv:
            saving = f"{(tv - sv) / tv:+.0%}"
        else:
            saving = "—"
        A(f"| {label} | {'—' if tv is None else fmt.format(tv)} | "
          f"{'—' if sv is None else fmt.format(sv)} | {saving} |")
    A("")

    warnings = []
    for arm in ARMS:
        s = summary[arm]
        if s["runs"] and s["runs"] < 3:
            warnings.append(f"`{arm}` has only {s['runs']} run(s) — indicative, "
                            f"not measured.")
        if s["missing_token_data"]:
            warnings.append(
                f"`{arm}`: {s['missing_token_data']} parity-passing run(s) had "
                f"no token data and are excluded from the cost means rather "
                f"than counted as zero.")
        if s["parity_passed"] == 0 and s["runs"]:
            warnings.append(f"`{arm}` never reached parity, so it has no "
                            f"comparable cost at all.")
    if warnings:
        A("## Caveats")
        A("")
        for w in warnings:
            A(f"- ⚠️ {w}")
        A("")

    A("---")
    A("")
    A("**How to read the saving.** It is a comparison of end-to-end cost "
      "between two routes that both reached the correct finding. It is not a "
      "context-size ratio: caching, turn count, and output tokens all move it, "
      "and none of them are visible in a payload measurement.")
    return "\n".join(L)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("raw_dir", type=Path)
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", type=Path)
    args = p.parse_args(argv)

    runs = load_runs(args.raw_dir)
    if not runs:
        raise SystemExit(f"no run.json files under {args.raw_dir}")
    summary = summarise(runs)

    text = (json.dumps({"summary": summary, "n_runs": len(runs)}, indent=2)
            if args.json else render(summary, runs))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
