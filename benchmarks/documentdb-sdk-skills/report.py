#!/usr/bin/env python3
"""Build the skills-effectiveness report from MSBench run output.

WHAT THIS PRODUCES
------------------
The headline table for the GTM story: does having the DocumentDB agent kit
installed change what an agent builds, and what does it cost?

    msbench-cli report --run_id <treatment-run> --output treatment.json
    msbench-cli report --run_id <control-run>   --output control.json
    python3 report.py --treatment treatment.json --control control.json

WHY BOTH ARMS ARE REQUIRED
--------------------------
This script REFUSES to emit a report from one arm. An absolute pass rate is
uninterpretable: "80% resolved" could mean the kit is excellent or that the task
is easy, and there is no way to tell them apart without a control. The only
publishable figure is the delta between `documentdb-sdk-skills` (kit installed,
never mentioned in the prompt) and `documentdb-sdk-skills-noskills` (identical
task, no skills).

INPUT SCHEMA
------------
`msbench-cli report --output <file>.json` emits `{"schema": {"id":
"msbench.report", "version": "2.x"}}` containing, among others:

    resolved            {benchmark: {instance: bool | "error"}}
    resolved_rate       overall resolution rate
    custom_metrics      {benchmark: {instance: {"values": {...}}}}
    pass_at_k_status    {complete, expected_attempts, ...}

The per-instance `values` are what `shared/verifier/harvest_metrics.py` wrote
into `custom_metrics.json` — token counts, AI credits, and per-category check
tallies.

COST FIGURES: READ `tokens_fresh_input`, NOT `tokens_input`
-----------------------------------------------------------
`cache_read_tokens` is a SUBSET of `input_tokens`, and a skill payload is sent
once then served from cache (measured: ~91% of input was cache reads). Quoting
raw input as "the cost of the skills" overstates it by roughly an order of
magnitude, so this report leads with fresh (uncached) input and shows the cache
share next to it.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

TREATMENT_DEFAULT = "documentdb-sdk-skills"
CONTROL_DEFAULT = "documentdb-sdk-skills-noskills"

# Metrics summarised per arm: (key, label, formatter)
COST_METRICS = [
    ("tokens_fresh_input", "Fresh input tokens", "{:,.0f}"),
    ("tokens_output", "Output tokens", "{:,.0f}"),
    ("ai_credits", "AI credits", "{:,.2f}"),
    ("agent_turns", "Turns", "{:,.1f}"),
    ("cache_read_share_pct", "Cache share %", "{:.1f}"),
]

CHECK_CATEGORIES = ["api", "behavior", "documentdb", "engine", "source", "skills"]
TEXT_CHUNK_BYTES = 6


def load(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"report not found: {path}")
    data = json.loads(path.read_text())
    schema = (data.get("schema") or {}).get("id")
    if schema and schema != "msbench.report":
        print(f"warning: unexpected schema {schema!r} in {path}", file=sys.stderr)
    return data


def _instances(report: dict, benchmark: str) -> dict:
    resolved = report.get("resolved") or {}
    if benchmark in resolved:
        return resolved[benchmark] or {}
    # Fall back to the only benchmark present, so a single-benchmark report
    # still works when the caller did not pin a name.
    keys = [k for k, v in resolved.items() if isinstance(v, dict)]
    if len(keys) == 1:
        return resolved[keys[0]] or {}
    raise SystemExit(
        f"benchmark {benchmark!r} not in report (found: {sorted(resolved)}). "
        f"Pass --treatment-benchmark / --control-benchmark."
    )


def _metrics(report: dict, benchmark: str) -> dict:
    cm = report.get("custom_metrics") or {}
    if benchmark in cm:
        return cm[benchmark]
    keys = list(cm)
    return cm[keys[0]] if len(keys) == 1 else {}


def decode_text_metrics(values: dict, prefix: str) -> str | None:
    """Reconstruct a string encoded as exact numeric custom metrics."""
    if not values.get(f"{prefix}_available"):
        return None
    length = int(values.get(f"{prefix}_utf8_len", 0))
    count = int(values.get(f"{prefix}_chunk_count", 0))
    data = bytearray()
    for index in range(count):
        key = f"{prefix}_chunk_{index:03d}"
        if key not in values:
            return None
        remaining = length - len(data)
        width = min(TEXT_CHUNK_BYTES, remaining)
        data.extend(int(values[key]).to_bytes(width, "big"))
    try:
        return bytes(data).decode("utf-8")
    except UnicodeDecodeError:
        return None


def summarise(report: dict, benchmark: str) -> dict:
    """Reduce one arm to pass rate + mean cost, per instance and overall."""
    instances = _instances(report, benchmark)
    metrics = _metrics(report, benchmark)

    # `resolved` values may be bool or the string "error"; only True counts as a
    # pass. Treating "error" as anything else would silently inflate the score.
    passed = [k for k, v in instances.items() if v is True]
    attempted = list(instances)

    collected: dict[str, list[float]] = {k: [] for k, _, _ in COST_METRICS}
    checks: dict[str, list[float]] = {}
    missing_tokens = 0
    provenance = {
        "model_ids": set(),
        "api_endpoints": set(),
        "reasoning_efforts": set(),
        "agent_identity": set(),
        "copilot_cli_version": set(),
    }
    missing_model_data = 0

    for inst in attempted:
        values = ((metrics.get(inst) or {}).get("values")) or {}
        if not values.get("tokens_available"):
            missing_tokens += 1
        for key, _, _ in COST_METRICS:
            if key in values:
                collected[key].append(float(values[key]))
        for cat in CHECK_CATEGORIES:
            p, t = values.get(f"checks_{cat}_passed"), values.get(f"checks_{cat}_total")
            if p is not None and t:
                checks.setdefault(cat, []).append(float(p) / float(t))
        for prefix in provenance:
            value = decode_text_metrics(values, prefix)
            if value:
                provenance[prefix].add(value)
        if not decode_text_metrics(values, "model_ids"):
            missing_model_data += 1

    return {
        "benchmark": benchmark,
        "instances": len(attempted),
        "passed": len(passed),
        "pass_rate": (len(passed) / len(attempted)) if attempted else None,
        "cost": {k: (statistics.mean(v) if v else None) for k, v in collected.items()},
        "cost_n": {k: len(v) for k, v in collected.items()},
        "check_rates": {c: statistics.mean(v) for c, v in checks.items()},
        "missing_token_data": missing_tokens,
        "missing_model_data": missing_model_data,
        "provenance": {key: sorted(values) for key, values in provenance.items()},
        "pass_at_k": report.get("pass_at_k_status") or {},
    }


def require_comparable_model_provenance(treatment: dict, control: dict) -> str:
    """Fail publication unless both arms observed one identical model set."""
    for arm in (treatment, control):
        if arm["missing_model_data"]:
            raise SystemExit(
                f"{arm['benchmark']} is missing observed model provenance for "
                f"{arm['missing_model_data']} instance(s)"
            )
        identities = arm["provenance"]["model_ids"]
        if len(identities) != 1:
            raise SystemExit(
                f"{arm['benchmark']} used inconsistent model identities: {identities}"
            )
    treatment_model = treatment["provenance"]["model_ids"][0]
    control_model = control["provenance"]["model_ids"][0]
    if treatment_model != control_model:
        raise SystemExit(
            "treatment and control used different models: "
            f"{treatment_model!r} vs {control_model!r}"
        )
    return treatment_model


def _pct(x):
    return "—" if x is None else f"{x:.0%}"


def _delta(t, c, fmt="{:+.1f}"):
    if t is None or c is None:
        return "—"
    return fmt.format(t - c)


def render(t: dict, c: dict) -> str:
    L = []
    A = L.append
    A("# DocumentDB agent kit — MSBench effectiveness report")
    A("")
    A("**The intervention being measured is: the DocumentDB agent kit's skills "
      "are installed and discoverable.** Everything else — task, prompt, model, "
      "agent, container, verifier — is identical between the two arms, so any "
      "difference is attributable to the kit.")
    A("")
    models = t.get("provenance", {}).get("model_ids") or []
    if len(models) == 1:
        shown_models = "`, `".join(models[0].splitlines())
        A(
            f"- **Observed model identifier(s):** `{shown_models}` "
            "(from the Copilot session store)"
        )
    endpoints = t.get("provenance", {}).get("api_endpoints") or []
    if len(endpoints) == 1:
        shown_endpoints = "`, `".join(endpoints[0].splitlines())
        A(f"- **Observed API endpoint(s):** `{shown_endpoints}`")
    efforts = t.get("provenance", {}).get("reasoning_efforts") or []
    if len(efforts) == 1:
        shown_efforts = "`, `".join(efforts[0].splitlines())
        A(f"- **Observed reasoning effort(s):** `{shown_efforts}`")
    agent_ids = t.get("provenance", {}).get("agent_identity") or []
    if len(agent_ids) == 1:
        A(f"- **Agent:** `{agent_ids[0]}`")
    cli_versions = t.get("provenance", {}).get("copilot_cli_version") or []
    if len(cli_versions) == 1:
        A(f"- **Observed Copilot CLI version:** `{cli_versions[0]}`")
    A(f"- **Treatment** (`{t['benchmark']}`): skills installed in the agent's "
      f"skills directory, and **never mentioned in the prompt** — this measures "
      f"whether an agent that merely *has* the kit applies it.")
    A(f"- **Control** (`{c['benchmark']}`): no skills installed. Nothing for the "
      f"agent to discover or read.")
    A("")
    pak = t.get("pass_at_k") or {}
    if pak:
        A(f"- **pass@k:** complete={pak.get('complete')} "
          f"expected_attempts={pak.get('expected_attempts')}")
        A("")

    A("## Headline")
    A("")
    A("| | Control | Treatment | Delta |")
    A("|---|---|---|---|")
    A(f"| Instances | {c['instances']} | {t['instances']} | |")
    A(f"| Resolved | {c['passed']} | {t['passed']} | "
      f"{t['passed'] - c['passed']:+d} |")
    A(f"| **Pass rate** | {_pct(c['pass_rate'])} | {_pct(t['pass_rate'])} | "
      f"{_delta(t['pass_rate'], c['pass_rate'], '{:+.0%}')} |")
    A("")

    A("## Cost")
    A("")
    A("What the kit costs. The control has no skill files to read, so the input "
      "delta is literally the price of the kit being available and used. Note "
      "that *more tokens per attempt is not the same as more expensive* — see "
      "credits per passing result below.")
    A("")
    A("| Metric | Control | Treatment | Delta |")
    A("|---|---|---|---|")
    for key, label, fmt in COST_METRICS:
        tv, cv = t["cost"].get(key), c["cost"].get(key)
        A(f"| {label} | {'—' if cv is None else fmt.format(cv)} | "
          f"{'—' if tv is None else fmt.format(tv)} | {_delta(tv, cv, '{:+,.1f}')} |")
    A("")

    # Cost per passing result: the ROI figure. Failed attempts are part of the
    # price of a success, so total credits are divided by PASSES, not runs.
    for arm in (c, t):
        credits, n = arm["cost"].get("ai_credits"), arm["instances"]
        arm["_cpp"] = (credits * n / arm["passed"]) if (credits and arm["passed"]) else None
    c_cpp = "—" if c["_cpp"] is None else f"{c['_cpp']:,.2f}"
    t_cpp = "—" if t["_cpp"] is None else f"{t['_cpp']:,.2f}"
    A("| Derived | Control | Treatment |")
    A("|---|---|---|")
    A(f"| **Credits per passing result** | {c_cpp} | {t_cpp} |")
    A("")
    A("*Credits per passing result* is the figure that matters: total spend "
      "divided by successes, so failed attempts are charged to the successes "
      "they paid for. An arm that costs more per attempt but passes far more "
      "often is cheaper where it counts.")
    A("")

    if t["check_rates"] or c["check_rates"]:
        A("## Where the difference shows up")
        A("")
        A("Per-category check pass rates. The kit should move the "
          "`documentdb`, `engine` and `source` rows — those encode the "
          "best-practice rules. `api` and `behavior` measure basic competence "
          "and should already be high in both arms.")
        A("")
        A("| Check category | Control | Treatment | Delta |")
        A("|---|---|---|---|")
        for cat in CHECK_CATEGORIES:
            tv, cv = t["check_rates"].get(cat), c["check_rates"].get(cat)
            if tv is None and cv is None:
                continue
            A(f"| `{cat}` | {_pct(cv)} | {_pct(tv)} | "
              f"{_delta(tv, cv, '{:+.0%}')} |")
        A("")

    warnings = []
    for arm in (t, c):
        if arm["missing_token_data"]:
            warnings.append(
                f"{arm['missing_token_data']}/{arm['instances']} instances in "
                f"`{arm['benchmark']}` had no token data "
                f"(`tokens_available=0`) — cost means exclude them rather than "
                f"counting them as zero.")
        if arm["instances"] < 3:
            warnings.append(
                f"`{arm['benchmark']}` has only {arm['instances']} instance(s); "
                f"agent runs are non-deterministic, so treat this as indicative "
                f"rather than a measurement.")
        if arm["missing_model_data"]:
            warnings.append(
                f"{arm['missing_model_data']}/{arm['instances']} instances in "
                f"`{arm['benchmark']}` had no observed model provenance."
            )
    if warnings:
        A("## Caveats")
        A("")
        for w in warnings:
            A(f"- ⚠️ {w}")
        A("")

    A("---")
    A("")
    A("**Reading note.** Cost is reported as *fresh* (uncached) input tokens. "
      "`cache_read_tokens` is a subset of `tokens_input`, and the skill payload "
      "is cached after first use, so raw input overstates the cost of the kit "
      "by roughly an order of magnitude.")
    return "\n".join(L)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--treatment", type=Path, required=True,
                   help="msbench-cli report JSON for the skills arm")
    p.add_argument("--control", type=Path, required=True,
                   help="msbench-cli report JSON for the no-skills arm")
    p.add_argument("--treatment-benchmark", default=TREATMENT_DEFAULT)
    p.add_argument("--control-benchmark", default=CONTROL_DEFAULT)
    p.add_argument("--out", type=Path)
    p.add_argument("--json", action="store_true",
                   help="emit the summary as JSON instead of markdown")
    args = p.parse_args(argv)

    t = summarise(load(args.treatment), args.treatment_benchmark)
    c = summarise(load(args.control), args.control_benchmark)
    require_comparable_model_provenance(t, c)

    if args.json:
        out = json.dumps({"treatment": t, "control": c}, indent=2, default=str)
    else:
        out = render(t, c)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(out + "\n")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
