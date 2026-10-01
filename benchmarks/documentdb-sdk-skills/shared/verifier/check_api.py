"""API conformance — does the service expose the contracted HTTP surface?

Weakest of the behavioural checks and deliberately first: if the API is wrong,
every later failure is a consequence rather than an independent finding, and
the per-check logs should make that obvious.

SDK-agnostic: no SDK token appears in a test name, so these run for every SDK.
"""
from __future__ import annotations

import pytest

from conftest import CONTRACT, ROOTS, fmt_path, root_ids


def test_health_endpoint_responds(api):
    path = CONTRACT.get("health_path", "/health")
    resp = api.get(path)
    assert resp.status_code == 200, (
        f"GET {path} returned {resp.status_code}, expected 200. The service must "
        f"expose a health endpoint so the harness can tell 'not started yet' "
        f"apart from 'started but broken'."
    )


@pytest.mark.parametrize("root", ROOTS, ids=root_ids)
class TestCreate:
    def test_create_accepts_contract_rows(self, root, seed_roots):
        results = seed_roots[root["name"]]
        bad = [r for r in results if r["status"] not in (200, 201)]
        assert not bad, (
            f"POST {root['create']['path']} rejected valid rows: "
            + ", ".join(f"{r['row']['id']} -> {r['status']}" for r in bad)
        )

    def test_duplicate_create_is_rejected(self, root, api, seed_roots):
        """A second create of the same id must not silently succeed.

        Accepting it would let an implementation overwrite or duplicate rows,
        which the behavioural check then catches as data corruption — better to
        name the cause here.
        """
        create = root.get("create")
        expected = create.get("duplicate_status", 409)
        row = root["seed"][0]
        resp = api.post(create["path"], json=row)
        assert resp.status_code == expected, (
            f"Re-POSTing existing {root['name']} {row['id']!r} returned "
            f"{resp.status_code}, expected {expected}."
        )


@pytest.mark.parametrize("root", ROOTS, ids=root_ids)
class TestRead:
    def test_get_by_id_returns_the_row(self, root, api, seed_roots):
        get = root.get("get")
        if not get:
            pytest.skip(f"{root['name']} has no GET-by-id endpoint")
        for row in root["seed"]:
            resp = api.get(fmt_path(get["path"], id=row["id"]))
            assert resp.status_code == 200, (
                f"GET {fmt_path(get['path'], id=row['id'])} -> {resp.status_code}"
            )
            body = resp.json()
            for field in root.get("compare_fields", []):
                assert body.get(field) == row.get(field), (
                    f"{root['name']} {row['id']}: API returned {field}="
                    f"{body.get(field)!r}, expected {row.get(field)!r}"
                )

    def test_get_unknown_id_is_404(self, root, api):
        get = root.get("get")
        if not get:
            pytest.skip(f"{root['name']} has no GET-by-id endpoint")
        resp = api.get(fmt_path(get["path"], id="definitely-not-a-real-id"))
        assert resp.status_code == 404, (
            f"GET of an unknown {root['name']} returned {resp.status_code}, "
            f"expected 404."
        )


@pytest.mark.parametrize("root", ROOTS, ids=root_ids)
class TestList:
    def test_filtered_list_returns_exactly_the_matching_rows(
        self, root, api, seed_roots
    ):
        """The filter is the query the whole benchmark is built around.

        Returning too many rows means the filter is ignored; too few means the
        query or the index is wrong. Both are graded here as a set comparison
        so ordering is not accidentally required.
        """
        lst = root.get("list")
        if not lst or not lst.get("filter_param"):
            pytest.skip(f"{root['name']} has no filtered list endpoint")

        field = lst["filter_field"]
        values = sorted({row[field] for row in root["seed"]})
        for value in values:
            resp = api.get(lst["path"], params={lst["filter_param"]: value})
            assert resp.status_code == 200, (
                f"GET {lst['path']}?{lst['filter_param']}={value} -> "
                f"{resp.status_code}"
            )
            body = resp.json()
            rows = body if isinstance(body, list) else body.get("items", body.get("data"))
            assert isinstance(rows, list), (
                f"Filtered list must return a JSON array (or an object with "
                f"'items'/'data'); got {type(body).__name__}"
            )
            got = {r.get("id") for r in rows}
            expected = {r["id"] for r in root["seed"] if r[field] == value}
            assert got == expected, (
                f"{lst['path']}?{lst['filter_param']}={value} returned {sorted(got)}, "
                f"expected {sorted(expected)}"
            )
