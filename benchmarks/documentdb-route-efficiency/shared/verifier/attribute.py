#!/usr/bin/env python3
"""Attribute token usage to individual subagent runs.

WHY THIS EXISTS
---------------
The cross-model matrix was blocked on `COPILOT_SDK_AUTH_TOKEN`, which Vally and
MSBench both need. It turns out the Copilot CLI's own subagents provide the same
three properties, with no extra credential:

  per-run isolation   each subagent runs in its own context window, so there is
                      no conversation carry-over between runs — the "clean
                      context" requirement, satisfied structurally rather than
                      by cleanup
  model selection     a subagent can be pinned to a specific model
  attribution         its usage lands in assistant_usage_events with a distinct
                      non-null `agent_id` (the spawning tool-call id), and
                      exactly one model per agent_id

Verified empirically: a probe subagent pinned to gemini-3.1-pro-preview produced
one row, agent_id=toolu_01MYbS4…, model=gemini-3.1-pro-preview, 6867 in / 3 out.
The orchestrating parent's own rows carry agent_id=NULL and are excluded.

USAGE
-----
    python3 attribute.py snapshot                 # before launching subagents
    ... run subagents ...
    python3 attribute.py collect --since <id> --out runs.json

WHAT THIS HARNESS IS NOT
------------------------
A subagent is not the MSBench or Vally executor: different scaffolding, system
prompt and tool surface. Absolute numbers from here are NOT comparable to an
MSBench run. They are comparable **within** this harness, which is all a
cross-model or cross-arm comparison needs, because everything except the varied
factor is held constant.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

DEFAULT_STORE = Path.home() / ".copilot" / "session-store.db"
NANO_AIU_PER_CREDIT = 1_000_000_000


def _open(db: Path):
    """Snapshot the store before reading; it is being written to live."""
    tmp = Path(tempfile.mkdtemp(prefix="attrib-"))
    snap = tmp / db.name
    shutil.copy2(db, snap)
    for suffix in ("-wal", "-shm"):
        side = db.with_name(db.name + suffix)
        if side.exists():
            shutil.copy2(side, snap.with_name(snap.name + suffix))
    conn = sqlite3.connect(f"file:{snap}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn, tmp


def snapshot(db: Path) -> int:
    conn, tmp = _open(db)
    try:
        row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m "
                           "FROM assistant_usage_events").fetchone()
        return int(row["m"])
    finally:
        conn.close()
        shutil.rmtree(tmp, ignore_errors=True)


def collect(db: Path, since: int) -> list[dict]:
    """One record per subagent run created after `since`.

    `agent_id IS NOT NULL` is what separates subagent spend from the
    orchestrator's own. Including the parent would swamp the measurement — its
    context is far larger than any subagent's.
    """
    conn, tmp = _open(db)
    try:
        rows = conn.execute(
            """
            SELECT agent_id,
                   MIN(model)                            AS model,
                   COUNT(*)                              AS requests,
                   COUNT(DISTINCT model)                 AS n_models,
                   COALESCE(SUM(input_tokens), 0)        AS input_tokens,
                   COALESCE(SUM(output_tokens), 0)       AS output_tokens,
                   COALESCE(SUM(cache_read_tokens), 0)   AS cache_read_tokens,
                   COALESCE(SUM(reasoning_tokens), 0)    AS reasoning_tokens,
                   COALESCE(SUM(total_nano_aiu), 0)      AS nano_aiu,
                   COALESCE(SUM(duration_ms), 0)         AS duration_ms,
                   MIN(id)                               AS first_id
            FROM assistant_usage_events
            WHERE id > ? AND agent_id IS NOT NULL
            GROUP BY agent_id
            ORDER BY first_id
            """,
            (since,),
        ).fetchall()
    finally:
        conn.close()
        shutil.rmtree(tmp, ignore_errors=True)

    out = []
    for r in rows:
        d = dict(r)
        inp, cache = d["input_tokens"], d["cache_read_tokens"]
        # cache_read is a SUBSET of input; fresh input is what is billed at the
        # uncached rate. Quoting raw input overstates cost by ~an order of
        # magnitude once a payload is cached.
        d["fresh_input_tokens"] = max(inp - cache, 0)
        d["cache_read_share_pct"] = round(100.0 * cache / inp, 2) if inp else 0.0
        d["ai_credits"] = round(d.pop("nano_aiu") / NANO_AIU_PER_CREDIT, 4)
        d["wall_secs"] = round(d.pop("duration_ms") / 1000.0, 1)
        # A subagent should use exactly one model. More than one means the run
        # was not what we think it was, so it is flagged rather than averaged.
        d["single_model"] = d.pop("n_models") == 1
        out.append(d)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--store", type=Path, default=DEFAULT_STORE)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snapshot")
    c = sub.add_parser("collect")
    c.add_argument("--since", type=int, required=True)
    c.add_argument("--out", type=Path)
    args = p.parse_args(argv)

    if not args.store.is_file():
        raise SystemExit(f"session store not found: {args.store}")

    if args.cmd == "snapshot":
        print(snapshot(args.store))
        return 0

    runs = collect(args.store, args.since)
    text = json.dumps(runs, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")
        print(f"wrote {args.out} ({len(runs)} subagent run(s))")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
