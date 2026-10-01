"""Importable renderer shim for the hyphenated CLI module."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = Path(__file__).with_name("toast-split-advisor-render.py")
_SPEC = importlib.util.spec_from_file_location("toast_split_advisor_renderer", _PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load renderer: {_PATH}")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

render = _MODULE.render
