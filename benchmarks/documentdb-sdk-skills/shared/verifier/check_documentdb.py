"""DocumentDB-level checks — modelling and indexing, read via pymongo.

These grade the decisions the kit's `documentdb-data-modeling` and
`documentdb-indexing` skills teach, observed in the actual collection rather
than in the source code:

  * a type discriminator and schemaVersion on documents (schema evolution)
  * ISO-8601 timestamps stored in a queryable form
  * at least one secondary index covering the query the API exposes
  * compound indexes ordered Equality -> Sort (ESR)

Index checks are structural, not source-based, so they hold regardless of which
driver or language the agent used.
"""
from __future__ import annotations

import re

import pytest

from conftest import ROOTS, collection_name, root_ids

ISO8601 = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$"
)


def _indexes(db, root):
    return list(db[collection_name(root)].list_indexes())


def _secondary(indexes):
    return [ix for ix in indexes if ix.get("name") != "_id_"]


@pytest.mark.parametrize("root", ROOTS, ids=root_ids)
class TestModelling:
    def test_documents_carry_a_type_discriminator(self, root, root_persisted):
        """Mixed-type collections are normal in DocumentDB; without a
        discriminator you cannot tell the shapes apart later."""
        if not root.get("modeling", {}).get("type_discriminator"):
            pytest.skip("not required by the contract")
        candidates = ("type", "_type", "docType", "doc_type", "entityType")
        for row in root["seed"]:
            doc = root_persisted[root["name"]][row["id"]]
            assert doc is not None, f"{row['id']} not persisted"
            assert any(doc.get(c) for c in candidates), (
                f"{root['name']} {row['id']} has no type discriminator "
                f"(looked for {candidates}). Documents should record what they "
                f"are so a collection can hold more than one shape safely."
            )

    def test_documents_carry_a_schema_version(self, root, root_persisted):
        if not root.get("modeling", {}).get("schema_version"):
            pytest.skip("not required by the contract")
        candidates = ("schemaVersion", "schema_version", "_schemaVersion", "v")
        for row in root["seed"]:
            doc = root_persisted[root["name"]][row["id"]]
            assert any(doc.get(c) is not None for c in candidates), (
                f"{root['name']} {row['id']} has no schema version "
                f"(looked for {candidates}). Without one, migrating a live "
                f"collection later means guessing which documents are old."
            )

    def test_timestamp_is_queryable(self, root, root_persisted):
        """Accept a BSON date or an ISO-8601 string; reject a bare epoch int or
        a locale-formatted string, both of which sort incorrectly."""
        field = root.get("modeling", {}).get("timestamp_field")
        if not field:
            pytest.skip("no timestamp field in the contract")
        import datetime as _dt
        for row in root["seed"]:
            doc = root_persisted[root["name"]][row["id"]]
            value = doc.get(field)
            assert value is not None, (
                f"{root['name']} {row['id']} has no {field!r}."
            )
            ok = isinstance(value, _dt.datetime) or (
                isinstance(value, str) and ISO8601.match(value)
            )
            assert ok, (
                f"{root['name']} {row['id']}: {field!r} is {value!r}. Store a "
                f"BSON date or an ISO-8601 string — other formats do not sort "
                f"or range-query correctly."
            )


@pytest.mark.parametrize("root", ROOTS, ids=root_ids)
class TestIndexing:
    def test_a_secondary_index_exists(self, root, db):
        if not root.get("indexing", {}).get("require_secondary_index"):
            pytest.skip("not required by the contract")
        secondary = _secondary(_indexes(db, root))
        assert secondary, (
            f"{collection_name(root)} has only the default _id index. The API "
            f"exposes a filtered query, so it will collection-scan on every "
            f"call as the collection grows."
        )

    def test_queried_fields_are_indexed(self, root, db):
        """Every field the API filters on must lead some index.

        Leading position matters: a field buried in the middle of a compound
        index cannot be used for an equality lookup on its own.
        """
        required = root.get("indexing", {}).get("required_query_fields", [])
        if not required:
            pytest.skip("no required query fields")
        leading = set()
        for ix in _secondary(_indexes(db, root)):
            keys = list(ix.get("key", {}).keys())
            if keys:
                leading.add(keys[0])
        missing = [f for f in required if f not in leading]
        assert not missing, (
            f"{collection_name(root)}: no index LEADS with {missing}. Existing "
            f"secondary indexes lead with {sorted(leading) or 'nothing'}. A "
            f"field that does not lead an index cannot serve an equality lookup."
        )

    def test_compound_index_follows_esr(self, root, db):
        """Equality keys must precede Sort keys in a compound index.

        This is the single most valuable rule in the indexing skill, and it is
        checkable structurally — no source parsing, no judgement.
        """
        esr = root.get("indexing", {}).get("esr_compound")
        if not esr:
            pytest.skip("no ESR expectation in the contract")
        equality, sort = esr["equality"], esr["sort"]

        compound = [ix for ix in _secondary(_indexes(db, root))
                    if len(ix.get("key", {})) > 1]
        if not compound:
            pytest.skip(
                "no compound index present; the single-field index requirement "
                "is graded separately"
            )

        offenders = []
        for ix in compound:
            keys = list(ix["key"].keys())
            for s in sort:
                if s not in keys:
                    continue
                s_pos = keys.index(s)
                for e in equality:
                    if e in keys and keys.index(e) > s_pos:
                        offenders.append((ix.get("name"), keys))
        assert not offenders, (
            f"Compound index does not follow ESR (Equality before Sort): "
            f"{offenders}. Expected equality {equality} to precede sort {sort}."
        )
