# Advanced e-commerce compatibility dataset

Deterministic, committed fixtures for testing three higher-risk
MongoDB-compatible surfaces in Azure DocumentDB:

1. Multi-document transactions
2. Change streams
3. Advanced aggregation stages and operators

The dataset is generated from source, validated without a database, and
committed as JSONL so the exact same bytes can later be loaded into MongoDB and
DocumentDB.

> These fixtures are for compatibility testing, not production sample data.

## Dataset

| Collection | Records | Test purpose |
|---|---:|---|
| `customers` | 200 | `$lookup`, segmentation, nested addresses |
| `products` | 100 | arrays, nested attributes, `$bucket`, `$sortArray` |
| `inventory` | 300 | transactional stock updates and contention |
| `orders` | 2,000 | grouping, window functions, date operators |
| `order_items` | 6,000 | one-to-many and correlated pipeline `$lookup` |
| `payments` | 2,000 | transaction consistency across collections |
| `returns` | 120 | `$unionWith` activity streams |
| `daily_sales` | 84 | 90-day series with 6 missing days and 3 null values for `$densify` / `$fill` |
| `stream_orders` | 2 | baseline documents for change-stream operations |

Additional case definitions:

| File | Cases |
|---|---:|
| `data/cases/transactions.json` | 4 |
| `data/cases/change-streams.json` | 4 operations |
| `data/cases/aggregations.json` | 7 |

## Transaction fixtures

All cases target one known inventory record in `WH_EAST`:

| Case | Product | Starting stock | Expected |
|---|---|---:|---|
| Successful purchase | `PROD_0001` | 10 | commit, stock becomes 8 |
| Concurrent last unit | `PROD_0002` | 1 | exactly one of two transactions commits |
| Insufficient stock | `PROD_0003` | 0 | rollback, no order/payment |
| Forced exception | `PROD_0004` | 25 | rollback after payment insert, stock remains 25 |

## Change-stream sequence

`data/cases/change-streams.json` defines a deterministic sequence against
`stream_orders`:

```text
insert → update → replace → delete
```

The later compatibility test should normalize server-specific fields such as
resume token, `clusterTime`, and `wallTime`, then compare operation type,
namespace, document key, update description, and full document.

## Advanced aggregation coverage

The case catalog covers:

- `$facet`
- Pipeline `$lookup` with `let` and `$expr`
- `$setWindowFields`
- `$densify` and `$fill`
- `$unionWith`
- `$bucket`
- `$dateTrunc`
- Array expressions: `$map`, `$filter`, `$reduce`, `$sortArray`
- `$merge`

## Reproduce the committed data

```bash
cd scenarios/ecommerce-advanced
npm ci

# Rewrite data/ from the deterministic generator.
npm run generate

# Validate hashes, counts, foreign keys, totals, and all edge-case fixtures.
npm run validate

# Generate twice in clean directories and require byte-identical output.
npm run check-determinism
```

Expected:

```text
{"status":"PASS","dataset":"ecommerce-advanced","version":"1.0.0",...}
PASS: two clean generations are byte-identical
```

The generator uses no wall clock and no `Math.random()`. Its seed, fixed
generation timestamp, and data epoch are recorded in `data/manifest.json`,
along with record counts, byte counts, and SHA-256 for every generated file.

### Generation result

Generated and validated on 2026-09-01:

```text
collections:
  customers=200
  products=100
  inventory=300
  orders=2000
  order_items=6000
  payments=2000
  returns=120
  daily_sales=84
  stream_orders=2

test cases:
  transactions=4
  change_streams=4
  aggregations=7

generated files=13
generated payload=2,225,666 bytes
validation=PASS
two-clean-generation diff=PASS
```

## Load into a MongoDB-compatible endpoint

```bash
export MONGODB_URI='<connection-string>'
export MONGODB_DATABASE='ecommerce_advanced'
npm run load
```

`load.mjs` converts the committed `{"$date":"..."}` values to BSON dates,
loads every collection, creates the indexes from `data/indexes.json`, and
verifies final counts. It drops all source collections first and also clears
the write-producing test targets `customer_summaries` and `stream_events`, so
previous `$merge` or change-stream runs cannot leak into the next test.

The committed files were also loaded into DocumentDB Local. All nine collection
counts matched the manifest, `orders.placed_at` and `daily_sales.sales_date`
were BSON dates, and every declared secondary index was created.

## Why this size

The dataset is large enough to exercise joins, grouping, windows, and
contention without turning compatibility tests into load tests. Correctness is
the purpose here; performance testing should use a separately scaled fixture.
