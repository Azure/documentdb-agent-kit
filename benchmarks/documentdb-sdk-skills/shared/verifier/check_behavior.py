"""Behavioural checks — the concrete, hard-to-game core of the grader.

For every declared root entity we:

    1. Seed deterministic rows through the agent's public HTTP API.
    2. Independently read the persisted documents straight from DocumentDB
       with the VERIFIER'S OWN client.
    3. Assert the API, the persisted documents and the contract all agree.

This catches what a source-code regex cannot: an app that answers HTTP but
stores nothing (in-memory dict, SQLite), a filter that returns the wrong rows,
or a "create" that silently overwrites duplicates.

Why this is the primary category: source checks tell you the agent *wrote*
something that looks right. Only this tells you the system *behaves* right.
"""
from __future__ import annotations

import pytest

from conftest import ROOTS, collection_name, fmt_path, root_ids


@pytest.mark.parametrize("root", ROOTS, ids=root_ids)
class TestPersistenceIsReal:
    """Every row POSTed through the API must exist as a real document."""

    def test_every_seeded_row_is_persisted(self, root, seed_roots, root_persisted):
        docs = root_persisted[root["name"]]
        missing = [r["id"] for r in root["seed"] if docs.get(r["id"]) is None]
        assert not missing, (
            f"These {root['name']} rows were accepted by the API but are NOT in "
            f"DocumentDB: {missing}. The service must persist through the "
            f"MongoDB driver — an in-memory or SQLite store that never writes to "
            f"the database fails this gate."
        )

    def test_persisted_fields_match_input(self, root, seed_roots, root_persisted):
        docs = root_persisted[root["name"]]
        for row in root["seed"]:
            doc = docs[row["id"]]
            assert doc is not None, f"{row['id']} not persisted"
            for field in root.get("compare_fields", []):
                assert doc.get(field) == row.get(field), (
                    f"{root['name']} {row['id']}: {field!r} stored as "
                    f"{doc.get(field)!r}, expected {row.get(field)!r} "
                    f"(arrays must round-trip in order)."
                )


@pytest.mark.parametrize("root", ROOTS, ids=root_ids)
class TestRoundTripIntegrity:
    """GET must return what is actually stored, not a cached copy that has
    drifted from the persisted document."""

    def test_api_read_matches_database(self, root, seed_roots, root_persisted, api):
        get = root.get("get")
        if not get:
            pytest.skip(f"{root['name']} has no GET-by-id endpoint")
        docs = root_persisted[root["name"]]
        for row in root["seed"]:
            doc = docs[row["id"]]
            resp = api.get(fmt_path(get["path"], id=row["id"]))
            assert resp.status_code == 200
            body = resp.json()
            for field in root.get("compare_fields", []):
                assert body.get(field) == doc.get(field), (
                    f"{root['name']} {row['id']}: API says {field}="
                    f"{body.get(field)!r} but the database holds {doc.get(field)!r}. "
                    f"The read path is not reading from the database."
                )


@pytest.mark.parametrize("root", ROOTS, ids=root_ids)
class TestNoDuplication:
    def test_duplicate_create_did_not_create_a_second_document(
        self, root, db, seed_roots, api
    ):
        """The duplicate POST in check_api must not have written a second row.

        Returning 409 while still inserting is a real bug this catches, and one
        an API-only grader would miss entirely.
        """
        create = root.get("create")
        if not create:
            pytest.skip("no create endpoint")
        row = root["seed"][0]
        api.post(create["path"], json=row)  # attempt another duplicate
        coll = db[collection_name(root)]
        count = coll.count_documents(
            {"$or": [{"_id": row["id"]}, {"id": row["id"]}]}
        )
        assert count == 1, (
            f"{root['name']} {row['id']!r} exists {count} times after duplicate "
            f"POSTs; expected exactly 1."
        )


@pytest.mark.parametrize("root", ROOTS, ids=root_ids)
class TestDataShape:
    """Types must survive the round trip.

    A numeric amount stored as a string is the single most common DocumentDB
    modelling error, it breaks range queries and index use silently, and the
    kit's data-modeling skill warns about it explicitly.
    """

    def test_numeric_fields_are_stored_as_numbers(self, root, root_persisted):
        for field in root.get("numeric_fields", []):
            for row in root["seed"]:
                doc = root_persisted[root["name"]][row["id"]]
                assert doc is not None
                value = doc.get(field)
                assert isinstance(value, (int, float)) and not isinstance(value, bool), (
                    f"{root['name']} {row['id']}: {field!r} stored as "
                    f"{type(value).__name__} ({value!r}), expected a number. "
                    f"Numbers stored as strings break range queries and index use."
                )

    def test_string_arrays_stay_arrays(self, root, root_persisted):
        for field in root.get("string_array_fields", []):
            for row in root["seed"]:
                doc = root_persisted[root["name"]][row["id"]]
                value = doc.get(field)
                assert isinstance(value, list), (
                    f"{root['name']} {row['id']}: {field!r} stored as "
                    f"{type(value).__name__}, expected an array."
                )
                assert all(isinstance(v, str) for v in value), (
                    f"{root['name']} {row['id']}: {field!r} must contain strings"
                )
