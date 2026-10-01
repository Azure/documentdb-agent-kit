#!/usr/bin/env python3
"""toast-split-advisor-render.py — build the TOAST-split advisor report.

Consumes the per-collection buffer that toast-split-advisor.sh assembles (one
tab-separated line per collection, either a FIELDJSON payload or "CLEAN"), passed
via environment variables, and prints either the human report or a compact JSON
object. Kept as a standalone module (not an inline heredoc) so it can be read,
linted, and tested on its own.

Env in: REPORT_DATA, JSON_MODE (0/1), DB_NAME, FIELD_MIN, INLINE_THR,
        TOAST_RATIO, MIN_KB.
"""

import json
import os
import sys
from typing import TextIO

def render(
    *,
    data: str,
    json_mode: bool,
    db_name: str,
    field_min: int,
    inline_threshold: int,
    toast_ratio: float,
    min_kb: str,
    output: TextIO = sys.stdout,
) -> None:
    findings = []
    clean = []

    for line in data.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 4)
        if len(parts) < 5:
            continue
        coll, heap, toast, total, tail = parts
        heap, toast, total = int(heap), int(toast), int(total)
        ratio = (toast / (heap + toast)) if (heap + toast) > 0 else 0.0

        if tail == "CLEAN":
            clean.append(
                {
                    "collection": coll,
                    "heap_bytes": heap,
                    "toast_bytes": toast,
                    "toast_ratio": round(ratio, 4),
                }
            )
            continue

        field_data = json.loads(tail)
        avg = field_data.get("avg_obj_size", 0) or 0
        fields = field_data.get("fields", [])
        candidates = [f for f in fields if f.get("b", 0) >= field_min]
        largest_only = (not candidates) and fields
        show = candidates if candidates else (fields[:1] if fields else [])
        moved_bytes = sum(f["b"] for f in candidates)
        projected_hot = max(avg - moved_bytes, 0)

        findings.append(
            {
                "collection": coll,
                "heap_bytes": heap,
                "toast_bytes": toast,
                "total_bytes": total,
                "toast_ratio": round(ratio, 4),
                "avg_obj_size": avg,
                "sampled_docs": field_data.get("sampled", 0),
                "split_candidates": [
                    {
                        "field": f["f"],
                        "avg_bytes": f["b"],
                        "pct_of_doc": round(100.0 * f["b"] / avg, 1)
                        if avg > 0
                        else 0.0,
                    }
                    for f in show
                ],
                "candidate_threshold_bytes": field_min,
                "no_field_over_threshold": bool(largest_only),
                "projected_hot_avg_bytes": projected_hot,
                "projected_stays_inline": projected_hot < inline_threshold,
                "recommended_side_collection": coll + "_ext",
                "side_collection_key": "_id",
                "note": "ANALYSIS ONLY — no data moved. Apply the split yourself.",
            }
        )

    if json_mode:
        print(
            json.dumps(
                {
                    "db": db_name,
                    "flagged": len(findings),
                    "findings": findings,
                    "clean": clean,
                    "analysis_only": True,
                }
            ),
            file=output,
        )
        return

    bar = "═" * 70
    print(bar, file=output)
    print(
        " DocumentDB TOAST Split Advisor  (ANALYSIS ONLY — does not modify data)",
        file=output,
    )
    print(
        f" Database: {db_name}   flag TOAST ratio > {toast_ratio}, min {min_kb}KB, "
        f"candidate field >= {field_min}B",
        file=output,
    )
    print(bar, file=output)
    print(file=output)

    for finding in findings:
        heap_kb = finding["heap_bytes"] // 1024
        toast_kb = finding["toast_bytes"] // 1024
        print(f"  ⚠️  {finding['collection']}", file=output)
        print(
            f"        heap={heap_kb}KB  TOAST={toast_kb}KB  "
            f"(TOAST ratio {finding['toast_ratio']})  "
            f"avgObjSize={finding['avg_obj_size']}B  "
            f"[sampled {finding['sampled_docs']} docs]",
            file=output,
        )
        if finding["no_field_over_threshold"]:
            big = (
                finding["split_candidates"][0]
                if finding["split_candidates"]
                else None
            )
            if big:
                print(
                    f"        no single field >= "
                    f"{finding['candidate_threshold_bytes']}B; largest is "
                    f"'{big['field']}' ({big['avg_bytes']}B, "
                    f"{big['pct_of_doc']}% of doc).",
                    file=output,
                )
            print(
                "        Bloat is spread across fields — review the schema "
                "rather than a single split.",
                file=output,
            )
        else:
            print(
                "        split candidate field(s) to MOVE into a side collection:",
                file=output,
            )
            for candidate in finding["split_candidates"]:
                print(
                    f"          • {candidate['field']:<24} "
                    f"~{candidate['avg_bytes']}B/doc  "
                    f"({candidate['pct_of_doc']}% of document)",
                    file=output,
                )
            inline = (
                "stays INLINE (TOAST≈0) ✅"
                if finding["projected_stays_inline"]
                else "still large — consider moving more fields ⚠️"
            )
            print(
                f"        after moving these, hot doc ≈ "
                f"{finding['projected_hot_avg_bytes']}B → {inline}",
                file=output,
            )
            print(
                f"        → create '{finding['recommended_side_collection']}' "
                f"keyed by '{finding['side_collection_key']}' holding those "
                f"fields; keep '{finding['collection']}' scalar-only.",
                file=output,
            )
        print(file=output)

    for item in clean:
        print(
            f"  ✅  {item['collection']}  heap={item['heap_bytes']//1024}KB "
            f"TOAST={item['toast_bytes']//1024}KB "
            f"(ratio {item['toast_ratio']}) — no bloat",
            file=output,
        )

    print(file=output)
    print("─" * 70, file=output)
    if not findings:
        print(
            "  ✅ No large-document/TOAST bloat detected — nothing to split.",
            file=output,
        )
        return

    print(
        f"  Flagged {len(findings)} collection(s). "
        "This tool ONLY reports guidance.",
        file=output,
    )
    print(file=output)
    print(
        "  Applying the split safely (DO NOT run a naive bulk update on a large",
        file=output,
    )
    print(
        "  collection — it bursts WAL, holds locks, and leaves dead-tuple bloat):",
        file=output,
    )
    print(
        "    1. Copy the candidate field(s) into the side collection, keyed by _id,",
        file=output,
    )
    print(
        "       in _id-range BATCHES (e.g. 10k docs) — copy BEFORE removing.",
        file=output,
    )
    print(
        "    2. Verify per batch that the side collection has the row, THEN $unset",
        file=output,
    )
    print(
        "       the field(s) from the hot collection for that batch.",
        file=output,
    )
    print(
        "    3. After migration, VACUUM (FULL, ANALYZE) the hot table to reclaim",
        file=output,
    )
    print(
        "       space (takes an exclusive lock + ~2x disk — schedule a window).",
        file=output,
    )
    print(
        "    4. Update the application to read the field(s) from the side",
        file=output,
    )
    print(
        "       collection on demand (extra _id lookup) — split only wins when the",
        file=output,
    )
    print(
        "       big field is read far less often than the scalars are scanned.",
        file=output,
    )


def main() -> None:
    render(
        data=os.environ.get("REPORT_DATA", ""),
        json_mode=os.environ.get("JSON_MODE", "0") == "1",
        db_name=os.environ.get("DB_NAME", ""),
        field_min=int(os.environ.get("FIELD_MIN", "1024")),
        inline_threshold=int(os.environ.get("INLINE_THR", "2000")),
        toast_ratio=float(os.environ.get("TOAST_RATIO", "0.5")),
        min_kb=os.environ.get("MIN_KB", "256"),
    )


if __name__ == "__main__":
    main()
