"""Canonicalisation helpers for the Diagnostic Regression Suite.

A diagnostic script is "deterministic" when the SAME database state yields the
SAME `--json` result. Two kinds of legitimate drift must be normalised away
first, or the assertion produces false failures:

1. **Volatile values** — live measurements (query latency, PostgreSQL hit ratios
   and scan counters). Removed entirely.
2. **Volatile ordering** — lists that are sorted by one of those volatile values
   can legitimately reorder. Sorted into a stable order; contents still compared.

Everything else is compared exactly, so a real nondeterminism bug (unsorted
output, dict ordering, sampling, parallel workers) still fails loudly.
"""

import json
import re


def canonicalise(value, volatile_fields, order_insensitive_lists=(),
                 sampled_count_maps=(), sampled_size_strings=(), _key=None):
    """Return a copy of `value` with volatile data normalised away.

    Args:
        value: parsed JSON (dict / list / scalar).
        volatile_fields: key names whose values are live measurements.
        order_insensitive_lists: key names whose list order is derived from a
            volatile metric and must therefore be normalised.
        sampled_count_maps: key names holding a {category: count} map produced by
            *sampling*. The categories are a stable finding; the counts are not,
            so counts are blanked while the category keys are preserved.
        sampled_size_strings: key names holding a summary string with sampled
            byte sizes (e.g. "body:4002B,notes:2002B"). The sizes are blanked;
            the field names and their order — the actual finding — are kept.
        _key: the key this value was found under (internal recursion detail).
    """
    volatile = set(volatile_fields)
    order_insensitive = set(order_insensitive_lists)
    sampled_maps = set(sampled_count_maps)
    sampled_sizes = set(sampled_size_strings)

    if isinstance(value, dict):
        if _key in sampled_maps:
            # Keep WHICH categories were observed (the actual finding); drop the
            # sampled counts (which vary run to run).
            return {k: "<sampled-count>" for k in sorted(value)}
        return {
            k: canonicalise(v, volatile, order_insensitive, sampled_maps,
                            sampled_sizes, _key=k)
            for k, v in sorted(value.items())
            if k not in volatile
        }

    if isinstance(value, list):
        items = [
            canonicalise(v, volatile, order_insensitive, sampled_maps,
                         sampled_sizes, _key=_key)
            for v in value
        ]
        if _key in order_insensitive:
            # Stable, content-based ordering — independent of how the script
            # happened to sort them on this run.
            items.sort(key=lambda item: json.dumps(item, sort_keys=True))
        return items

    if isinstance(value, str) and _key in sampled_sizes:
        # "body:4002B,notes:2002B,title:13B" -> "body:<B>,notes:<B>,title:<B>"
        return re.sub(r"\d+B\b", "<B>", value)

    return value


def canonical_json(value, volatile_fields, order_insensitive_lists=(),
                   sampled_count_maps=(), sampled_size_strings=()):
    """Canonicalise and render as a stable JSON string for comparison/diffing."""
    return json.dumps(
        canonicalise(value, volatile_fields, order_insensitive_lists,
                     sampled_count_maps, sampled_size_strings),
        sort_keys=True,
        indent=2,
    )


def is_empty_result(canonical):
    """True when a canonicalised result carries no findings at all.

    Guards against 'false determinism': a script that reports nothing is
    trivially identical across runs, which proves nothing.
    """
    if canonical is None:
        return True
    if isinstance(canonical, (list, dict)):
        return len(canonical) == 0
    return False
