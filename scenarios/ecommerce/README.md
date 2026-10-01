# ecommerce demo dataset

Seeds `ecommerce` — a realistic store dataset (customers, products, orders,
order_items, reviews, inventory, categories, suppliers) large enough to exercise
the diagnostic toolbox: `perf-advisor.sh`, `index-redundancy-finder.sh`, and
`data-integrity-check.sh`.

## Files

| File | What it is |
|------|-----------|
| `seed.sh` | Self-contained seeder (embeds the data-generation script; ~50K orders, ~150K order_items). |
| [`../../compat/`](../../compat/QUICKSTART.md) | MongoDB-compatible Node.js workload running end-to-end on DocumentDB, including three `$lookup` queries and exact-result verification. |
| [`../ecommerce-advanced/`](../ecommerce-advanced/README.md) | Deterministic committed data for transactions, change streams, and advanced aggregation compatibility tests. |

## Run

```bash
export DB_PASSWORD=Test1234                 # or pass --password
bash scenarios/ecommerce/seed.sh            # -> database "ecommerce"

bash scripts/perf-advisor.sh          --db ecommerce
bash scripts/index-redundancy-finder.sh --db ecommerce
bash scripts/data-integrity-check.sh  --db ecommerce
```

Prereq: a running `documentdb-local` container — see the repo
[`README.md`](../../README.md#quickstart) *Quickstart*. Overrides: `--container`,
`--password`, `--db`, or the `DB_USER`/`DB_PASSWORD`/`PORT` env vars.
