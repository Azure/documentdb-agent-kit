# ecommerce demo dataset

Seeds `ecommerce` — a realistic store dataset (customers, products, orders,
order_items, reviews, inventory, categories, suppliers) large enough to exercise
the diagnostic toolbox: `perf-advisor.sh`, `index-redundancy-finder.sh`, and
`data-integrity-check.sh`.

## Files

| File | What it is |
|------|-----------|
| `seed.sh` | Self-contained seeder (embeds the data-generation script; ~50K orders, ~150K order_items). |

## Run

```bash
export DB_PASSWORD='<your-password>'                 # or pass --password
bash scenarios/ecommerce/seed.sh            # -> database "ecommerce"

bash scripts/perf-advisor.sh          --db ecommerce
bash scripts/index-redundancy-finder.sh --db ecommerce
bash scripts/data-integrity-check.sh  --db ecommerce

# query-performance skill before/after test (COLLSCAN -> IXSCAN on orders)
bash scenarios/ecommerce/query-perf-skill-test.sh
```

The query-perf test harness (`query-perf-skill-test.js` / `.sh`) validates the
query-performance skills against this dataset: for each case it forces a
`COLLSCAN` baseline, creates the index that skill recommends, re-measures, and
drops it again — so it is idempotent. For a guided walkthrough of the same
before/after, see [`docs/quickstart-find-and-fix-slow-queries.md`](../../docs/quickstart-find-and-fix-slow-queries.md).

Prereq: a running `documentdb-local` container — see the repo
[`README.md`](../../README.md#quickstart) *Quickstart*. Overrides: `--container`,
`--password`, `--db`, or the `DB_USER`/`DB_PASSWORD`/`PORT` env vars.
