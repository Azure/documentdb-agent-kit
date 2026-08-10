# index-redundancy demo dataset

Seeds `idx_test` — a database with **intentionally redundant and unused indexes**
(prefix-redundant, exact-duplicate, unique-shadowed, reverse-variant, and unused)
so [`index-redundancy-finder.sh`](../../scripts/index-redundancy-finder.sh) has
findings to report.

## Files

| File | What it is |
|------|-----------|
| `fixture-redundant-indexes.js` | mongosh seeder: 3 collections (`users`, `orders`, `sessions`) with planted index redundancies. |
| `seed.sh` | Wrapper — copies the fixture into the container and loads it into `idx_test`. |

## Run

```bash
export DB_PASSWORD='<your-password>'                       # or pass --password
bash scenarios/index-redundancy/seed.sh           # -> database "idx_test"
bash scripts/index-redundancy-finder.sh --db idx_test
bash scripts/index-redundancy-finder.sh --db idx_test --json    # machine output
```

Prereq: a running `documentdb-local` container — see the repo
[`README.md`](../../README.md#quickstart) *Quickstart*. Overrides: `--container`,
`--password`, `--db`, or the `DB_USER`/`DB_PASSWORD`/`PORT` env vars.
