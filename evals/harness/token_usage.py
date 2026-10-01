#!/usr/bin/env python3
"""Task-level token / AI-credit accounting for Cross-Model Skill Evaluations.

WHY THIS EXISTS
---------------
Cross-Model Skill Evaluations ask two questions about the text skills: *is the
output good* and *what did it cost*. Vally answers both, but only when a real
model executor is available. This module answers the cost half from data the
Copilot CLI already writes locally, so cost can be measured today and
cross-checked against Vally later. It is stdlib-only and read-only.

Source: ``~/.copilot/session-store.db`` (SQLite), table
``assistant_usage_events`` — one row per model request:

    session_id, turn_index, agent_id, parent_tool_call_id, model,
    input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
    reasoning_tokens, total_nano_aiu, request_multiplier, duration_ms, ...

THE MEASUREMENT TRAP THIS MODULE IS BUILT TO AVOID
--------------------------------------------------
Skills add input tokens by construction — they are extra context. So
"skills use more tokens" is trivially true and says nothing about whether they
are worth it. Two corrections make the number honest:

1. ``cache_read_tokens`` is a SUBSET of ``input_tokens`` (verified: 0 of 6,348
   rows had cache_read > input). A skill payload is sent once and then read from
   cache, so raw ``input_tokens`` massively overstates its marginal cost. We
   report ``fresh_input = input - cache_read`` as the tokens actually paid for
   at full rate, and ``cache_read_share`` to show the amortisation.

2. The comparison that matters is COST-TO-OUTCOME, not cost-per-turn. A run that
   costs more per turn but needs fewer turns to reach a passing result is
   cheaper. Hence ``credits_to_green`` / ``turns_to_green``, which require an
   outcome to be supplied alongside the usage data.

``total_nano_aiu`` is the money column (AI Credits, 1e9 nano-AIU = 1 credit) and
already accounts for ``request_multiplier``, so it is comparable across models
in a way raw token counts are not.

USAGE
-----
    # what sessions exist
    python3 token_usage.py sessions --limit 10

    # one task's usage, as a JSON artifact
    python3 token_usage.py report --session <id> \
        --task orders-api --model claude-opus-5 --arm skills --run 3 \
        --outcome-passed 38 --outcome-total 40

    # aggregate many artifacts into the arm-vs-arm comparison table
    python3 token_usage.py compare results/*.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import statistics
import sys
import tempfile
from pathlib import Path

DEFAULT_DB = Path.home() / ".copilot" / "session-store.db"

NANO_AIU_PER_CREDIT = 1_000_000_000


# --------------------------------------------------------------------------
# database access
# --------------------------------------------------------------------------
def _open_readonly(db_path: Path) -> tuple[sqlite3.Connection, Path]:
    """Open a private snapshot of the session store.

    The CLI may be writing to this database while we read it. Opening the live
    file read-only can still fail or read a torn state mid-checkpoint, so we
    copy the database together with its -wal and -shm sidecars into a temp dir
    and read the copy. Copying only the .db would silently lose every
    transaction still sitting in the write-ahead log.
    """
    if not db_path.exists():
        raise SystemExit(
            f"Session store not found: {db_path}\n"
            "Token accounting requires generation to be driven by the Copilot "
            "CLI (see the plan, §3b path A). Pass --db if it lives elsewhere."
        )

    tmpdir = Path(tempfile.mkdtemp(prefix="tokenusage-"))
    snapshot = tmpdir / db_path.name
    shutil.copy2(db_path, snapshot)
    for suffix in ("-wal", "-shm"):
        sidecar = db_path.with_name(db_path.name + suffix)
        if sidecar.exists():
            shutil.copy2(sidecar, snapshot.with_name(snapshot.name + suffix))

    conn = sqlite3.connect(f"file:{snapshot}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn, tmpdir


def _cleanup(conn: sqlite3.Connection, tmpdir: Path | None) -> None:
    conn.close()
    if tmpdir:
        shutil.rmtree(tmpdir, ignore_errors=True)


# --------------------------------------------------------------------------
# core rollup
# --------------------------------------------------------------------------
_ROLLUP_SQL = """
SELECT
    COUNT(*)                                AS requests,
    COUNT(DISTINCT turn_index)              AS turns,
    COALESCE(SUM(input_tokens), 0)          AS input_tokens,
    COALESCE(SUM(output_tokens), 0)         AS output_tokens,
    COALESCE(SUM(cache_read_tokens), 0)     AS cache_read_tokens,
    COALESCE(SUM(cache_write_tokens), 0)    AS cache_write_tokens,
    COALESCE(SUM(reasoning_tokens), 0)      AS reasoning_tokens,
    COALESCE(SUM(total_nano_aiu), 0)        AS nano_aiu,
    COALESCE(SUM(duration_ms), 0)           AS duration_ms
FROM assistant_usage_events
WHERE session_id = ?
"""


def _derive(row: dict) -> dict:
    """Add the derived metrics that make the raw counters interpretable."""
    inp = row["input_tokens"]
    cache = row["cache_read_tokens"]
    # cache_read is a subset of input (verified), so this is the input actually
    # billed at the uncached rate — the real marginal cost of the context.
    fresh = max(inp - cache, 0)
    row["fresh_input_tokens"] = fresh
    row["cache_read_share"] = round(cache / inp, 4) if inp else 0.0
    row["credits"] = round(row["nano_aiu"] / NANO_AIU_PER_CREDIT, 4)
    row["wall_secs"] = round(row["duration_ms"] / 1000.0, 1)
    return row


def session_usage(conn: sqlite3.Connection, session_id: str) -> dict | None:
    row = conn.execute(_ROLLUP_SQL, (session_id,)).fetchone()
    if row is None or row["requests"] == 0:
        return None
    return _derive(dict(row))


def by_model(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    """Per-model split. A session can span models; costs are not comparable
    across them, so never sum credits across models without saying so."""
    sql = _ROLLUP_SQL.replace(
        "FROM assistant_usage_events", ", model FROM assistant_usage_events"
    ) + " GROUP BY model ORDER BY model"
    return [_derive(dict(r)) for r in conn.execute(sql, (session_id,))]


def by_agent(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    """Main-agent vs subagent split.

    Subagent spend is real spend. Reporting only the main agent would understate
    the cost of any skill that delegates.
    """
    sql = _ROLLUP_SQL.replace(
        "FROM assistant_usage_events",
        ", COALESCE(agent_id, 'main') AS agent FROM assistant_usage_events",
    ) + " GROUP BY agent ORDER BY agent"
    return [_derive(dict(r)) for r in conn.execute(sql, (session_id,))]


def list_sessions(conn: sqlite3.Connection, limit: int) -> list[dict]:
    sql = """
    SELECT s.id, s.repository, s.branch, s.created_at,
           COUNT(u.id)                        AS requests,
           COALESCE(SUM(u.total_nano_aiu), 0) AS nano_aiu
    FROM sessions s
    LEFT JOIN assistant_usage_events u ON u.session_id = s.id
    GROUP BY s.id
    HAVING requests > 0
    ORDER BY s.created_at DESC
    LIMIT ?
    """
    out = []
    for r in conn.execute(sql, (limit,)):
        d = dict(r)
        d["credits"] = round(d.pop("nano_aiu") / NANO_AIU_PER_CREDIT, 2)
        out.append(d)
    return out


# --------------------------------------------------------------------------
# report artifact
# --------------------------------------------------------------------------
def build_report(conn: sqlite3.Connection, session_id: str, task: dict,
                 outcome: dict | None) -> dict:
    usage = session_usage(conn, session_id)
    if usage is None:
        raise SystemExit(
            f"No usage rows for session {session_id!r}.\n"
            "Check the id with: token_usage.py sessions"
        )

    models = by_model(conn, session_id)
    report = {
        "task": task,
        "session_id": session_id,
        "models": [m["model"] for m in models],
        "usage": usage,
        "by_model": models,
        "by_agent": by_agent(conn, session_id),
    }

    if outcome:
        report["outcome"] = outcome
        green = outcome.get("green")
        # Cost-to-green is only meaningful for a run that actually reached
        # green. Emitting it for a failed run would flatter the failure — a run
        # that gives up early looks "cheap". Left null instead, deliberately.
        report["cost_to_green"] = {
            "green": green,
            "credits_to_green": usage["credits"] if green else None,
            "turns_to_green": usage["turns"] if green else None,
            "tokens_to_green": (
                usage["fresh_input_tokens"] + usage["output_tokens"]
                if green else None
            ),
        }
    return report


# --------------------------------------------------------------------------
# comparison across runs
# --------------------------------------------------------------------------
def _mean_sd(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "sd": None}
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 2),
        "sd": round(statistics.stdev(values), 2) if len(values) > 1 else 0.0,
    }


def compare(reports: list[dict]) -> dict:
    """Group run artifacts by (model, arm) and summarise each cell.

    N per cell is reported explicitly: agent runs are non-deterministic, and a
    mean over 1 run is not a result. Cells with n < 3 are flagged rather than
    quietly presented as if they were comparable.
    """
    cells: dict[tuple[str, str], list[dict]] = {}
    for r in reports:
        key = (r["task"].get("model") or "?", r["task"].get("arm") or "?")
        cells.setdefault(key, []).append(r)

    rows = []
    for (model, arm), runs in sorted(cells.items()):
        passed = [r for r in runs if r.get("outcome", {}).get("green")]
        credits = [r["usage"]["credits"] for r in runs]
        turns = [float(r["usage"]["turns"]) for r in runs]
        fresh = [float(r["usage"]["fresh_input_tokens"]) for r in runs]
        share = [r["usage"]["cache_read_share"] for r in runs]
        rows.append({
            "model": model,
            "arm": arm,
            "runs": len(runs),
            "underpowered": len(runs) < 3,
            "pass_rate": round(len(passed) / len(runs), 3) if runs else None,
            "credits": _mean_sd(credits),
            "turns": _mean_sd(turns),
            "fresh_input_tokens": _mean_sd(fresh),
            "cache_read_share": _mean_sd(share),
            # The ROI number: what one passing result costs. Undefined when
            # nothing passed — reported as null, never as 0 or infinity.
            "credits_per_pass": (
                round(sum(credits) / len(passed), 2) if passed else None
            ),
        })
    return {"cells": rows}


def render_table(comparison: dict) -> str:
    hdr = (
        "| Model | Arm | N | Pass rate | Credits (mean±sd) | Turns | "
        "Fresh input tok | Cache share | Credits/pass |"
    )
    sep = "|---|---|---|---|---|---|---|---|---|"
    lines = [hdr, sep]
    for c in comparison["cells"]:
        flag = " ⚠️" if c["underpowered"] else ""
        cr, tn, fi, cs = (c["credits"], c["turns"],
                          c["fresh_input_tokens"], c["cache_read_share"])
        pass_rate = "—" if c["pass_rate"] is None else f"{c['pass_rate']:.0%}"
        cpp = "—" if c["credits_per_pass"] is None else c["credits_per_pass"]
        lines.append(
            f"| {c['model']} | {c['arm']} | {c['runs']}{flag} | {pass_rate} | "
            f"{cr['mean']}±{cr['sd']} | {tn['mean']}±{tn['sd']} | "
            f"{fi['mean']:,.0f} | {cs['mean']:.0%} | {cpp} |"
        )
    if any(c["underpowered"] for c in comparison["cells"]):
        lines.append("")
        lines.append("⚠️ = fewer than 3 runs in this cell; treat as indicative only.")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Task-level token / AI-credit accounting for Cross-Model Skill Evaluations."
    )
    p.add_argument("--db", type=Path, default=DEFAULT_DB,
                   help=f"session store path (default: {DEFAULT_DB})")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sessions", help="list sessions that have usage data")
    s.add_argument("--limit", type=int, default=20)

    r = sub.add_parser("report", help="emit a per-task usage artifact")
    r.add_argument("--session", required=True)
    r.add_argument("--task", default=None, help="scenario / task name")
    r.add_argument("--model", default=None)
    r.add_argument("--arm", default=None, choices=["skills", "control"])
    r.add_argument("--run", type=int, default=None)
    r.add_argument("--outcome-passed", type=int, default=None)
    r.add_argument("--outcome-total", type=int, default=None)
    r.add_argument("--out", type=Path, default=None)

    c = sub.add_parser("compare", help="aggregate report artifacts into a table")
    c.add_argument("reports", nargs="+", type=Path)
    c.add_argument("--json", action="store_true", help="emit JSON, not markdown")

    args = p.parse_args(argv)

    if args.cmd == "compare":
        reports = [json.loads(f.read_text()) for f in args.reports]
        result = compare(reports)
        print(json.dumps(result, indent=2) if args.json else render_table(result))
        return 0

    conn, tmpdir = _open_readonly(args.db)
    try:
        if args.cmd == "sessions":
            for row in list_sessions(conn, args.limit):
                print(f"{row['id']}  {row['created_at']}  "
                      f"{row['requests']:>5} req  {row['credits']:>10.2f} cr  "
                      f"{row.get('repository') or ''}")
            return 0

        outcome = None
        if args.outcome_total is not None:
            passed = args.outcome_passed or 0
            outcome = {
                "tests_passed": passed,
                "tests_total": args.outcome_total,
                "green": passed == args.outcome_total and args.outcome_total > 0,
            }

        report = build_report(
            conn,
            args.session,
            {"task": args.task, "model": args.model,
             "arm": args.arm, "run": args.run},
            outcome,
        )
        text = json.dumps(report, indent=2)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text)
            print(f"wrote {args.out}", file=sys.stderr)
        else:
            print(text)
        return 0
    finally:
        _cleanup(conn, tmpdir)


if __name__ == "__main__":
    raise SystemExit(main())
