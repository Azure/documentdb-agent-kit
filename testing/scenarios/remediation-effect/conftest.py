"""Scenario conftest: seed the remediation-effect fixture."""

from pathlib import Path

from conftest_base import make_seeded_db_fixture

seeded_db = make_seeded_db_fixture(
    "test_remediation_effect",
    Path(__file__).resolve().parent,
)
