r"""Source-code checks — the STATIC, deliberately WEAKER half of the grader.

IMPORTANT: these are regex scans over the agent's source with comments
stripped (see `_strip_comments` in conftest.py). String *literals* are NOT
stripped, so every pattern here requires code adjacency (`foo\s*=`,
`Foo\s*\(`) rather than a bare keyword a log line could satisfy by accident.

WHY SO FEW CHECKS LIVE HERE
---------------------------
The Cosmos benchmark has ~520 lines of source checks because a single-node
emulator cannot prove client configuration behaviourally, so most of its
rubric has nowhere else to go.

We are not in that position. DocumentDB lets the verifier read the
PostgreSQL engine underneath, so index usage, scan behaviour and connection
reuse are graded BEHAVIOURALLY in check_engine.py. This file is therefore
small on purpose: only properties that genuinely leave no runtime trace stay
here. Prefer adding a check to check_engine.py or check_behavior.py whenever
the behaviour is observable.

The rules asserted here come from the kit's `documentdb-driver`,
`documentdb-connection` and `documentdb-data-modeling` skills.
"""
from __future__ import annotations

import ast
import re

import pytest


def _need(sdk: str, *want: str):
    if sdk not in want:
        pytest.skip(f"does not apply to {sdk} (only: {', '.join(want)})")


ROUTE_DECORATORS = {"get", "post", "put", "delete", "patch", "route"}
# Decorators that make a per-call construction safe because the result is
# memoised, or that mark application start-up.
CACHING_DECORATORS = {"lru_cache", "cache", "cached_property",
                      "on_event", "lifespan", "before_first_request"}


def _client_calls_inside_functions(source_files) -> list[str]:
    """Find MongoClient constructions that are NOT module-level singletons.

    Uses the AST rather than a regex. The regex version of this check had
    catastrophic backtracking — nested quantifiers over lines — and hung the
    verifier for minutes on a 6 KB file. Parsing is exact and ~1000x faster.

    WHY "ANY FUNCTION" AND NOT "ANY ROUTE HANDLER":
    an earlier version only looked inside route-decorated functions, and a
    deliberately naive submission slipped through by hiding the construction in
    a helper:

        def coll():
            c = MongoClient(...)          # a NEW pool on every request
            return c[db][collection]

        @app.get("/orders")
        def list_orders(): return list(coll().find(...))

    That is the exact anti-pattern the check exists to catch. A correct
    singleton is built once at module import (or behind an explicit cache /
    start-up hook), so anything else is reported.
    """
    offenders = []
    for path in source_files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except (SyntaxError, OSError):
            continue

        # Map every node to its enclosing function, if any.
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            exempt = False
            for dec in node.decorator_list:
                call = dec.func if isinstance(dec, ast.Call) else dec
                name = getattr(call, "attr", None) or getattr(call, "id", None)
                if name in CACHING_DECORATORS:
                    exempt = True
                    break
            if exempt:
                continue

            for inner in ast.walk(node):
                if (isinstance(inner, ast.Call)
                        and isinstance(inner.func, ast.Name)
                        and inner.func.id == "MongoClient"):
                    offenders.append(
                        f"{path.name}:{inner.lineno} in {node.name}()")
    return offenders


class TestClientLifecycle:
    """Singleton client.

    A MongoClient owns a connection pool. Constructing one per request
    exhausts server connections under load and defeats pooling entirely —
    the single most common driver mistake, and what `documentdb-driver` and
    `documentdb-connection` both open with.

    check_engine.py checks the runtime consequence; this names the cause.
    """

    def test_client_is_not_constructed_per_request(self, sdk, source_files):
        _need(sdk, "python")
        offenders = _client_calls_inside_functions(source_files)
        assert not offenders, (
            f"A MongoClient is constructed inside a function "
            f"({', '.join(offenders[:5])}), so a new connection pool is created "
            f"on every call. Build ONE client at application start-up and reuse "
            f"it — per-request construction exhausts server connections and "
            f"defeats pooling entirely. (A memoised factory, e.g. @lru_cache, "
            f"is also accepted.)"
        )

    def test_a_client_is_constructed_somewhere(self, sdk, source_text):
        _need(sdk, "python")
        assert re.search(r"MongoClient\s*\(", source_text), (
            "No MongoClient construction found in the source. The service must "
            "talk to DocumentDB through the MongoDB driver."
        )


class TestConnectionConfiguration:
    """Explicit pool and timeout settings.

    Defaults are not wrong, but an unset serverSelectionTimeoutMS means a
    database blip surfaces as a 30-second hang rather than a fast error. The
    `documentdb-connection` skill is entirely about making these explicit.
    """

    def test_connection_options_are_set_explicitly(self, sdk, source_text):
        _need(sdk, "python")
        options = (
            r"maxPoolSize", r"minPoolSize", r"serverSelectionTimeoutMS",
            r"connectTimeoutMS", r"socketTimeoutMS", r"retryWrites",
        )
        found = [o for o in options if re.search(o + r"\s*=", source_text)]
        assert found, (
            "MongoClient is constructed with no explicit connection options. "
            f"Set at least one of {', '.join(options)} — relying on defaults "
            "means a database blip becomes a long hang instead of a fast error."
        )


class TestTlsHygiene:
    """TLS must not be silently disabled.

    Azure DocumentDB requires TLS. Turning off certificate validation to make
    a local container work, then shipping it, is a real and common failure —
    and exactly what the `documentdb-security` skill warns about.
    """

    def test_certificate_validation_is_not_hardcoded_off(self, sdk, source_text):
        _need(sdk, "python")
        offenders = re.findall(
            r"tlsAllowInvalidCertificates\s*=\s*True|"
            r"tlsInsecure\s*=\s*True",
            source_text,
        )
        if offenders:
            # Allowed only when driven by an environment variable, which is how
            # a local-vs-cloud difference should be expressed.
            env_driven = re.search(
                r"tlsAllowInvalidCertificates\s*=\s*[^,\n)]*(?:os\.environ|getenv|"
                r"os\.getenv|settings\.|config\.)",
                source_text,
            )
            assert env_driven, (
                "TLS certificate validation is disabled with a hardcoded True "
                f"({offenders[:3]}). Azure DocumentDB requires TLS; if a local "
                "container needs a relaxed setting, drive it from an environment "
                "variable so production cannot inherit it."
            )
