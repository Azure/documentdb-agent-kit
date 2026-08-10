# model-large-field-split

**Category:** Data Modeling · **Priority:** HIGH

## Why it matters

In DocumentDB every document is stored as a **single BSON column** in PostgreSQL.
When a document carries a large, low-compressibility field (long free text, logs,
blobs), PostgreSQL pushes the value **out-of-line into a TOAST table** once the row
exceeds ~2 KB. Because the whole document is one column, reading **any** scalar
field detoasts the **entire** document — so a scan or aggregation that only needs
`status` or `amount` still pays to read all the big text. This "detoast tax" is
invisible to `explain` plan shape and **cannot be removed with an index** (even a
covering index still `FETCH`es and detoasts the row) or with a projection
(projection is applied *after* the server detoasts the row).

The fix is a **vertical split**: move the large field into a side collection keyed
by `_id`, so the hot collection stays small and inline, and the big field is read
only on demand.

## Incorrect

Large varied text co-located with the fields BI/list/aggregate queries scan:

```javascript
// opportunities — scanned constantly for pipeline/rollup aggregations
{
  _id: 4211,
  est_value: 82000, state: "open", territory_id: 7,   // <- what queries read
  narrative: "…3,500 chars of notes…",                 // <- big, rarely read
  activity_log: "…2,500 chars…"                        // <- big, rarely read
}
// Every {$group by territory, $sum est_value} detoasts ~6 KB per document.
```

## Correct

Keep the hot collection scalar-only; move the big text to a side collection:

```javascript
// opportunities  (hot, small, stays inline)
{ _id: 4211, est_value: 82000, state: "open", territory_id: 7 }

// opportunities_ext  (cold, fetched by _id only when the detail is opened)
{ _id: 4211, narrative: "…", activity_log: "…" }
```

Scans of `opportunities` no longer touch TOAST; the big text is read only via an
explicit `_id` lookup when a record's detail is actually needed.

**When NOT to split:** if the big field is read *together with* the scalars on
almost every access (e.g. a detail-record workload), co-location is correct — the
split just adds a second lookup. Split only when the cold field is read far less
often than the hot scalars are scanned.

## Companion tool

[`scripts/toast-split-advisor.sh`](../../scripts/toast-split-advisor.sh) **measures**
this condition on a live local container and reports **where** to split — it does
**not** move data:

```bash
bash scripts/toast-split-advisor.sh --db <name> [--json]
```

It reads real heap vs TOAST bytes from PostgreSQL, ranks the per-field split
candidates, projects whether the hot document will drop below the ~2 KB TOAST
threshold after the split, and prints safe (batched, copy-before-delete, then
`VACUUM`) migration guidance. Applying the split is an operator decision.

## References

- Related: [model-embed-vs-reference](model-embed-vs-reference.md) (reference unbounded / independently-accessed data), [model-16mb-limit](model-16mb-limit.md).
- `storage/` skill for the PostgreSQL storage layer; `query-optimizer/` for verifying scan cost with `explain("executionStats")`.
