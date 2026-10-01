#!/usr/bin/env python3
"""Harvest agent token usage and emit MSBench custom metrics.

WHY
---
MSBench's reward is binary: did the submission comply, yes or no. That answers
"is the kit effective?" but not "what did it cost?" — and cost is half the GTM
story. It also cannot tell us *which kinds of task* are expensive, which is
exactly the comparison we want across a growing task matrix.

MSBench has a first-class hook for this: an agent or verifier may write
`custom_metrics.json` into the instance output directory (`$OUTPUT_DIR`,
default `/output`). MSBench ingests it, derives a schema, and surfaces the
values per instance in `msbench-cli report --output <file>.json` and in CSV.
Real-world examples from the platform's own tests: `Tool_Calls_Total`,
`Files_Changed`, `msbench.agent_elapsed_time_sec`.

The `msbench-agent-github-copilot-cli` agent does NOT emit token metrics, so
we harvest them ourselves from the Copilot CLI's own session store, which the
agent leaves behind in the container.

WHAT IT READS
-------------
`~/.copilot/session-store.db` (SQLite), table `assistant_usage_events` — one
row per model request, carrying input/output/cache/reasoning token counts and
`total_nano_aiu` (AI credits x 1e9).

THE MEASUREMENT TRAP THIS AVOIDS
--------------------------------
`cache_read_tokens` is a SUBSET of `input_tokens` (verified against a real
store: 0 of 6,348 rows had cache_read > input). Skills are sent once and then
read from cache, so raw `input_tokens` overstates their marginal cost by
roughly 20x. We therefore emit `tokens_fresh_input = input - cache_read` as
the honest "billed at full rate" figure, alongside the raw counts and the
cache share, so a reader cannot accidentally quote the misleading number.

All emitted values are NUMERIC. MSBench infers a `numeric` schema from the
values, and a string would produce an inconsistent schema across instances.
Model identifiers, API endpoints, reasoning effort, agent identity, and the
observable Copilot CLI version are encoded losslessly into six-byte integer
chunks. `report.py` reconstructs them and refuses to publish a treatment/control
comparison when model provenance is missing or differs.

This is intentionally self-contained (stdlib only, no imports from the kit):
it has to run inside a minimal task container. `testing/scenarios/benchmark-metrics/`
asserts it agrees with `evals/harness/token_usage.py` on identical input, so
the two cost definitions cannot drift apart.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

NANO_AIU_PER_CREDIT = 1_000_000_000
TEXT_CHUNK_BYTES = 6
AGENT_IDENTITY = "msbench-agent-github-copilot-cli"

# Where the Copilot CLI keeps its session store. The agent may run as root or
# as another user depending on how the runner invokes it, so try each.
CANDIDATE_STORES = [
    "~/.copilot/session-store.db",
    "/root/.copilot/session-store.db",
    "/home/agent/.copilot/session-store.db",
    "/agent/.copilot/session-store.db",
]

ROLLUP_SQL = """
SELECT
    COUNT(*)                             AS requests,
    COUNT(DISTINCT turn_index)           AS turns,
    COALESCE(SUM(input_tokens), 0)       AS input_tokens,
    COALESCE(SUM(output_tokens), 0)      AS output_tokens,
    COALESCE(SUM(cache_read_tokens), 0)  AS cache_read_tokens,
    COALESCE(SUM(cache_write_tokens), 0) AS cache_write_tokens,
    COALESCE(SUM(reasoning_tokens), 0)   AS reasoning_tokens,
    COALESCE(SUM(total_nano_aiu), 0)     AS nano_aiu,
    COALESCE(SUM(duration_ms), 0)        AS duration_ms
FROM assistant_usage_events
"""


def encode_text_metrics(prefix: str, value: str) -> dict[str, int]:
    """Encode UTF-8 losslessly as JSON-safe integers.

    MSBench custom metrics are numeric-only. Six bytes fit below 2^48, so every
    chunk remains exactly representable by both JSON numbers and IEEE-754
    doubles while still allowing the report to reconstruct the exact string.
    """
    data = value.encode("utf-8")
    metrics = {
        f"{prefix}_available": 1 if data else 0,
        f"{prefix}_utf8_len": len(data),
        f"{prefix}_chunk_count": (len(data) + TEXT_CHUNK_BYTES - 1)
        // TEXT_CHUNK_BYTES,
    }
    for index in range(0, len(data), TEXT_CHUNK_BYTES):
        chunk = data[index : index + TEXT_CHUNK_BYTES]
        metrics[f"{prefix}_chunk_{index // TEXT_CHUNK_BYTES:03d}"] = int.from_bytes(
            chunk, "big"
        )
    return metrics


def observed_values(conn: sqlite3.Connection, column: str) -> list[str]:
    allowed = {"model", "api_endpoint", "reasoning_effort"}
    if column not in allowed:
        raise ValueError(f"unsupported provenance column: {column}")
    try:
        rows = conn.execute(
            f"SELECT DISTINCT {column} FROM assistant_usage_events "
            f"WHERE {column} IS NOT NULL AND {column} <> '' ORDER BY {column}"
        )
    except sqlite3.OperationalError:
        return []
    return [str(row[0]) for row in rows]


def copilot_cli_version() -> str:
    executable = shutil.which("copilot")
    if not executable:
        return ""
    try:
        result = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (result.stdout or result.stderr).strip().splitlines()[0]


def find_store(explicit: str | None = None) -> Path | None:
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.is_file() else None
    for candidate in CANDIDATE_STORES:
        p = Path(candidate).expanduser()
        if p.is_file():
            return p
    return None


def read_usage(db_path: Path) -> dict:
    """Roll up usage from a private snapshot of the store.

    The store is copied with its -wal/-shm sidecars before reading: copying
    only the .db would silently lose any transaction still sitting in the
    write-ahead log, which is exactly where the final turns live.
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="tokenharvest-"))
    try:
        snapshot = tmpdir / db_path.name
        shutil.copy2(db_path, snapshot)
        for suffix in ("-wal", "-shm"):
            sidecar = db_path.with_name(db_path.name + suffix)
            if sidecar.exists():
                shutil.copy2(sidecar, snapshot.with_name(snapshot.name + suffix))

        conn = sqlite3.connect(f"file:{snapshot}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            tables = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "assistant_usage_events" not in tables:
                return {}
            row = dict(conn.execute(ROLLUP_SQL).fetchone() or {})
            model_ids = observed_values(conn, "model")
            api_endpoints = observed_values(conn, "api_endpoint")
            reasoning_efforts = observed_values(conn, "reasoning_effort")
        finally:
            conn.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    if not row or not row.get("requests"):
        return {}

    inp = int(row["input_tokens"])
    cache = int(row["cache_read_tokens"])
    fresh = max(inp - cache, 0)
    metrics = {
        "agent_requests": int(row["requests"]),
        "agent_turns": int(row["turns"]),
        "tokens_input": inp,
        "tokens_output": int(row["output_tokens"]),
        "tokens_cache_read": cache,
        "tokens_cache_write": int(row["cache_write_tokens"]),
        "tokens_reasoning": int(row["reasoning_tokens"]),
        # The honest marginal cost: input actually billed at the uncached rate.
        "tokens_fresh_input": fresh,
        "tokens_billable_total": fresh + int(row["output_tokens"]),
        "cache_read_share_pct": round(100.0 * cache / inp, 2) if inp else 0.0,
        "ai_credits": round(int(row["nano_aiu"]) / NANO_AIU_PER_CREDIT, 4),
        "agent_wall_secs": round(int(row["duration_ms"]) / 1000.0, 1),
        "model_count": len(model_ids),
        "api_endpoint_count": len(api_endpoints),
        "reasoning_effort_count": len(reasoning_efforts),
    }
    metrics.update(encode_text_metrics("model_ids", "\n".join(model_ids)))
    metrics.update(encode_text_metrics("api_endpoints", "\n".join(api_endpoints)))
    metrics.update(
        encode_text_metrics("reasoning_efforts", "\n".join(reasoning_efforts))
    )
    metrics.update(encode_text_metrics("agent_identity", AGENT_IDENTITY))
    metrics.update(encode_text_metrics("copilot_cli_version", copilot_cli_version()))
    return metrics


def read_ctrf(path: Path) -> dict:
    """Per-check-category pass/fail counts from the verifier's CTRF report.

    This is what makes the token numbers actionable: it lets us ask which
    CATEGORY of requirement (api / behavior / documentdb / engine / source /
    skills) an expensive run was actually failing, rather than only how much it
    cost overall.
    """
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}

    tests = (data.get("results") or {}).get("tests") or []
    out: dict[str, float] = {}
    total = passed = 0
    per_category: dict[str, list[int]] = {}

    for test in tests:
        name = str(test.get("name", ""))
        status = str(test.get("status", "")).lower()
        if status == "skipped":
            continue
        total += 1
        ok = 1 if status == "passed" else 0
        passed += ok
        category = "other"
        for key in ("api", "behavior", "documentdb", "engine", "source", "skills"):
            if f"check_{key}" in name:
                category = key
                break
        bucket = per_category.setdefault(category, [0, 0])
        bucket[0] += ok
        bucket[1] += 1

    out["checks_total"] = total
    out["checks_passed"] = passed
    out["checks_failed"] = total - passed
    for category, (ok, tot) in sorted(per_category.items()):
        out[f"checks_{category}_passed"] = ok
        out[f"checks_{category}_total"] = tot
    return out


def build_metrics(store: Path | None, ctrf: Path, reward_file: Path) -> dict:
    metrics: dict[str, float] = {}

    usage = read_usage(store) if store else {}
    metrics.update(usage)
    # Explicitly record whether token data was available. Without this, a run
    # where harvesting failed is indistinguishable from a run that used no
    # tokens — and a silent zero would corrupt any average computed over it.
    metrics["tokens_available"] = 1 if usage else 0

    metrics.update(read_ctrf(ctrf))

    reward = 0
    if reward_file.is_file():
        try:
            reward = int((reward_file.read_text().strip() or "0")[:1])
        except ValueError:
            reward = 0
    metrics["reward"] = reward

    # Cost-to-outcome, only for a run that actually succeeded. Emitting it for
    # a failed run would make giving up early look cheap.
    if reward == 1 and usage:
        metrics["credits_to_green"] = usage["ai_credits"]
        metrics["turns_to_green"] = usage["agent_turns"]
        metrics["billable_tokens_to_green"] = usage["tokens_billable_total"]

    return metrics


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--store", default=os.environ.get("COPILOT_SESSION_STORE"),
                   help="path to session-store.db (default: autodetect)")
    p.add_argument("--ctrf",
                   default=os.path.join(
                       os.environ.get("VERIFIER_LOG_DIR", "/logs/verifier"),
                       "ctrf.json"))
    p.add_argument("--reward",
                   default=os.path.join(
                       os.environ.get("VERIFIER_LOG_DIR", "/logs/verifier"),
                       "reward.txt"))
    p.add_argument("--output-dir", default=os.environ.get("OUTPUT_DIR", "/output"))
    args = p.parse_args(argv)

    store = find_store(args.store)
    metrics = build_metrics(store, Path(args.ctrf), Path(args.reward))

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "custom_metrics.json"

    # Merge rather than overwrite: the agent may have written its own metrics
    # into the same file, and clobbering them would lose data MSBench expects.
    existing = {}
    if out_file.is_file():
        try:
            existing = json.loads(out_file.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            existing = {}
    existing.update(metrics)
    out_file.write_text(json.dumps(existing, indent=2, sort_keys=True))

    print(f"[harvest] wrote {out_file}")
    if store:
        print(f"[harvest] session store: {store}")
    else:
        print("[harvest] NOTE: no Copilot session store found; token metrics "
              "omitted and tokens_available=0.", file=sys.stderr)
    for k in sorted(metrics):
        print(f"[harvest]   {k} = {metrics[k]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
