"""Engine-level checks — the second observation plane.

WHY THIS FILE IS THE DIFFERENTIATOR
-----------------------------------
The Cosmos benchmark notes that client-side properties "a single-node local
emulator CANNOT prove behaviorally" have to be checked with static source-code
regex instead. That is the right call given their platform — a static check is
better than no coverage — but it is inherently easier to satisfy accidentally
than a runtime observation.

DocumentDB lets us avoid the trade-off. It is MongoDB-compatible on the
surface and PostgreSQL underneath, and the verifier can talk to BOTH. So
instead of grepping for `create_index(` and hoping, we ask the engine what
actually happened:

  * `explain()` through the Mongo API  -> was the query planned as an index
    scan, and how many documents did it read per document returned?
  * `pg_stat_user_indexes`             -> did the index actually get USED, or
                                          is it dead weight that only costs
                                          write throughput?

An agent can fake the source. It cannot fake the engine's own statistics.

THE METRIC: SCAN AMPLIFICATION
------------------------------
`totalDocsExamined / nReturned`. Raw "documents examined" is the wrong metric
on this engine: measured on DocumentDB Local, the planner picks an index scan
even for very unselective predicates, so `examined` mostly reflects how many
rows legitimately match rather than whether the index helped.

    amount > 490 (selective)    IXSCAN  examined=760    returned=760
    amount > 10  (unselective)  IXSCAN  examined=19960  returned=19960

Both are healthy — they read only rows they return. Amplification captures
that independently of selectivity.

DELIBERATELY NOT GRADED
-----------------------
Index-backed SORT and covered queries. The DocumentDB gateway pins the
experimental GUCs that enable them (`enableIndexOrderbyPushdown`,
`enableNewCompositeIndexOpClass`, `defaultUseCompositeOpClass`) off per
session, and `ALTER SYSTEM` plus an index rebuild does not change the
Mongo-API plan. Grading advice the harness cannot demonstrate would be worse
than not grading it.
"""
from __future__ import annotations

import pytest

from conftest import ROOTS, collection_name, database_name, root_ids


def _plan_stages(node, limit=30):
    stages, guard = [], 0
    while node and guard < limit:
        guard += 1
        stage = node.get("stage")
        if stage:
            stages.append(stage)
        node = node.get("inputStage") or (
            node.get("inputStages")[0] if node.get("inputStages") else None
        )
    return stages


def _explain(db, root, filt):
    coll = collection_name(root)
    plan = db.command({
        "explain": {"find": coll, "filter": filt},
        "verbosity": "executionStats",
    })
    stats = plan.get("executionStats", {}) or {}
    examined = int(stats.get("totalDocsExamined", 0) or 0)
    returned = int(stats.get("nReturned", 0) or 0)
    return {
        "stages": _plan_stages((plan.get("queryPlanner") or {}).get("winningPlan")),
        "examined": examined,
        "returned": returned,
        "amplification": (examined / returned) if returned else float("inf"),
    }


@pytest.mark.parametrize("root", ROOTS, ids=root_ids)
class TestQueryPlan:
    """Prove the index is USED, not merely created."""

    def test_filtered_query_is_not_a_full_collection_scan(
        self, root, db, seed_roots, bulk_filler
    ):
        fields = root.get("engine", {}).get("forbid_full_scan_for", [])
        if not fields:
            pytest.skip("no engine expectations in the contract")

        for field in fields:
            value = root["seed"][0][field]
            plan = _explain(db, root, {field: value})
            assert plan["returned"] > 0, (
                f"The probe {{{field}: {value!r}}} matched no documents, so it "
                f"cannot grade anything. Seeding likely failed."
            )
            assert "COLLSCAN" not in plan["stages"], (
                f"Query on {field!r} was planned as a COLLSCAN "
                f"(stages={plan['stages']}). An index exists only if it is "
                f"actually usable by the query the API issues."
            )

    def test_scan_amplification_is_low(self, root, db, seed_roots, bulk_filler):
        """The headline engine metric: documents read per document returned."""
        engine = root.get("engine", {})
        cap = engine.get("max_scan_amplification")
        fields = engine.get("forbid_full_scan_for", [])
        if cap is None or not fields:
            pytest.skip("no amplification expectation in the contract")

        for field in fields:
            value = root["seed"][0][field]
            plan = _explain(db, root, {field: value})
            assert plan["amplification"] <= cap, (
                f"Query on {field!r} read {plan['amplification']:.1f} documents "
                f"per document returned (examined={plan['examined']}, "
                f"returned={plan['returned']}), above the {cap}x limit. The "
                f"query is scanning rows it then throws away."
            )


@pytest.mark.parametrize("root", ROOTS, ids=root_ids)
class TestEngineStatistics:
    """Read PostgreSQL's own counters. This is the plane a Mongo-API-only
    grader — and the Cosmos benchmark — cannot see."""

    def test_a_secondary_index_actually_served_a_read(
        self, root, pg, db, seed_roots, bulk_filler
    ):
        """An index that is never scanned is pure write tax.

        `pg_stat_user_indexes.idx_scan` is the engine's own count of how many
        times each index was used, so this cannot be satisfied by declaring an
        index the queries never touch.
        """
        # Issue the query the API exposes so the counters have something to show.
        fields = root.get("engine", {}).get("forbid_full_scan_for", [])
        for field in fields:
            list(db[collection_name(root)].find({field: root["seed"][0][field]}))

        with pg.cursor() as cur:
            cur.execute(
                """
                SELECT indexrelname, idx_scan
                FROM pg_stat_user_indexes
                WHERE schemaname LIKE %s
                ORDER BY idx_scan DESC
                """,
                ("documentdb_data%",),
            )
            rows = cur.fetchall()

        assert rows, (
            "No DocumentDB index statistics found in pg_stat_user_indexes. The "
            "collection may live in an unexpected schema, or nothing was written."
        )
        used = [(name, scans) for name, scans in rows if (scans or 0) > 0]
        assert used, (
            "Not one index recorded a single scan "
            f"({[(n, s) for n, s in rows][:8]}). Every read is going through a "
            "sequential scan, so any index that exists is costing writes and "
            "buying nothing."
        )

    def test_collection_is_not_scan_dominated(
        self, root, pg, db, seed_roots, bulk_filler
    ):
        """Sequential scans are not always wrong — on a tiny table they are
        cheaper. This only fails when there is measurable index usage nowhere
        while sequential scans dominate, i.e. the access pattern is wrong in a
        way that will not improve with scale.
        """
        with pg.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(seq_scan), 0), COALESCE(SUM(idx_scan), 0)
                FROM pg_stat_user_tables
                WHERE schemaname LIKE %s
                """,
                ("documentdb_data%",),
            )
            seq, idx = cur.fetchone()

        if (seq or 0) + (idx or 0) == 0:
            pytest.skip("no table statistics recorded yet")
        assert (idx or 0) > 0, (
            f"Every access was a sequential scan (seq_scan={seq}, idx_scan={idx}). "
            f"The schema or the indexes do not match the queries the API issues."
        )
