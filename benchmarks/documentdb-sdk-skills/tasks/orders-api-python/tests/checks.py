"""orders-api-python task-specific checks.

The shared library (/verifier/check_*.py) already covers the whole rubric for
Python. This file is intentionally tiny — add Python-specific assertions here
if the skill set grows a Python-only rule.

It also guarantees pytest has a file to collect from /tests even when no
task-specific assertions exist, so a missing /tests/checks.py cannot silently
reduce the graded surface.
"""
from __future__ import annotations


def test_python_task_marker(sdk):
    assert sdk == "python"
