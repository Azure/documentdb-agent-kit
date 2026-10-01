# Scaling benchmark (optional / advanced)

> **Not part of the quickstart.** These scripts seed **multiple** databases at
> increasing scale (x1, x2, x4, x6, x8, x16) and run repeated benchmarks. They
> take time and disk, and are meant for investigating how the TOAST detoast tax
> grows with data size — not for a first run. For the ready-to-run demo use the
> single base-size dataset via [`../seed.sh`](../seed.sh).

## Contents

| File | What it does |
|------|-------------|
| `scale-bench2.sh` | Kill-tolerant harness: seeds `contoso_x{1,2,4,6,8,16}` and times the BI query suite at each scale. |
| `contoso-probe.js` | Single-query survivable timing probe (used by the harness). |
| `toast-index-bench.sh` | Sweeps index configurations (`_id`-only, single, compound, covering-attempt, group-only) before/after the schema split, recording PostgreSQL block traffic (the detoast tax). |
| `toast-index-probe.js` | The per-config explain + timing probe the bench runs. |
| `results.tsv` | Captured scaling results (x1…x16). **Generated output — git-ignored; recreated by `scale-bench2.sh`.** |
| `diagnostic-report-contoso-scaling.md` | Full write-up of the scaling + before/after-split findings. |
| `bench-queries.js`, `bench-seed-deterministic.js` | Older engine-comparison benchmark (MongoDB vs DocumentDB) — deterministic seed + query timing. |

## Key finding (summary)

Under the co-located schema the canonical BI aggregation's PostgreSQL block reads
scale with the TOASTed text, not the scalars it queries; a **covering index
cannot avoid it** (it still `FETCH`es and detoasts the full document). Splitting
the large text into a side collection keyed by `_id` collapses block reads
(~75× on the selective query, ~57× full-scan) — **schema shape beats index
tuning** for this class of problem. Details in
`diagnostic-report-contoso-scaling.md`.

## Run (advanced)

```bash
# seeds contoso_x1..x16 and benchmarks each (slow; needs the container up)
bash scenarios/contoso/scaling-benchmark/scale-bench2.sh

# before/after-split index matrix on a chosen scaled DB
bash scenarios/contoso/scaling-benchmark/toast-index-bench.sh --db contoso_x16 --phase before
```
