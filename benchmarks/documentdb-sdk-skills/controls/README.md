# Control submissions

Reference submissions used to validate that the **grader discriminates**. They
are not part of the benchmark an agent sees; they exist so the numbers in
[`../docs/REPORT.md`](../docs/REPORT.md) can be reproduced.

| Control | Expected reward | What it proves |
|---|---|---|
| *(empty `/app`)* | **0** | the harness notices missing deliverables |
| [`naive-python/`](naive-python/) | **0** | **the grader separates best practice from basic competence** |
| [`../tasks/orders-api-python/environment/reference/`](../tasks/orders-api-python/environment/reference/) (the oracle) | **1** | the grader can be satisfied at all |

Run all three with [`../verify-controls.sh`](../verify-controls.sh).

## Why `naive-python` is the important one

An empty `/app` scoring 0 proves very little — only that missing files are
noticed. A grader that *only* rejects empty submissions would be useless.

`naive-python` is **fully functional**. It implements every endpoint correctly,
persists to DocumentDB, rejects duplicates with 409, and returns the right rows
for a filtered query. It passes **every** API and behavioural check.

What it does *not* do is follow any DocumentDB best practice:

- no secondary index at all, so the hot-path query is a collection scan
- no type discriminator, no `schemaVersion`, no timestamp
- a **new `MongoClient` per request**, hidden inside a `coll()` helper, so every
  call builds a fresh connection pool
- no explicit pool or timeout settings
- `tlsAllowInvalidCertificates=True` hardcoded rather than env-driven

Measured result: **20/30, reward 0** — 12/12 on competence, 3/13 on best
practice. That gap is the benchmark's entire reason to exist, and this fixture
is what demonstrates it.

## It has already earned its keep

The per-request client in `coll()` was **not** caught by the first version of
the singleton check, which only inspected route-decorated functions. This
fixture is what exposed that blind spot; the check now examines any function
and the regression is pinned in `testing/scenarios/benchmark-config/`.

That is the argument for keeping a *working-but-wrong* control rather than only
an empty one: it probes the grader where the grader is actually weak.
