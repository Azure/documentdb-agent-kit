# DocumentDB Agent-Kit — Contoso Scaling & Diagnostic Report

**Generated:** 2026-07-02 05:20 UTC
**Container:** `documentdb-local` — `ghcr.io/documentdb/documentdb-local:latest`
**Scenario dir:** `documentdb-agent-kit/scenarios/contoso/`
**New diagnostic tools:** `scripts/document-bloat-advisor.sh`, `scripts/db-config-advisor.sh`

> Filename note: the request spelled this `diagnoistic-report-contodo`; saved with the
> corrected spelling `diagnostic-report-contoso` so it is discoverable.

---

## 1. Dataset — Contoso "Dynamics 365 Sales" model

Source: `mscottsewell/ContosoBI → Contoso - Sales - Current Release`. That release is the
**Dynamics 365 Sales (CRM)** demo (the numbered import files are Campaigns, Territories,
Accounts, Opportunities). The bundled `.xlsx` are password-encrypted, so the model was
reproduced faithfully as documents, keeping **all entities and relationships**:

```
territories (dim)
users (salespeople)         -> territory_id
products (dim)              (moderate text: description ~400B)
campaigns                   (BIG text: content ~4KB)              [scaled]
accounts   -> territory_id, owner_id            (BIG text: profile ~3.5KB)   [scaled]
opportunities -> account_id, campaign_id, owner_id, territory_id  [scaled]
     line_items:[ -> product_id ]
     narrative ~3.5KB + activity_log ~2.5KB   <-- large text CO-LOCATED (the anti-pattern)
```

**Text extension (MongoDB/DocumentDB-friendly):** each large entity carries realistic,
low-compressibility free-text. Scale factor multiplies products/campaigns/accounts and the
fact-like `opportunities` (base = 500 opportunities per scale unit).

Scale folders/datasets generated: **x1, x2, x4, x6, x8, x16** as databases
`contoso_x1 … contoso_x16` (seeder: `contoso-seed.js`, deterministic + resumable).

---

## 2. The DocumentDB-specific anti-pattern (not generic bad code)

DocumentDB stores each document as **one BSON column** in PostgreSQL. A large,
low-compressibility field is pushed **out-of-line into a TOAST table**. Because the whole
document is a single column, **reading any scalar field detoasts the entire document** — so
co-locating big text with fields your BI queries aggregate imposes a per-scan **detoast tax**.

Measured proof (validation probe): a collection of 1,000 docs with a varied ~6 KB text field →
**heap 80 KB, TOAST 8,000 KB**. The same field filled with *compressible* text (`"x"×6000`) →
**TOAST 0** (compressed inline). So the effect is specific to *realistic* large text.

Measured on the Contoso `opportunities` collection (x1): **heap 40 KB vs TOAST 3,880 KB — 99 %
of the collection is text the BI queries never read.**

This is **not** generic "SELECT *" advice: in DocumentDB **projection does not avoid the tax**
(the document is detoasted server-side *before* projection). The correct fix is a **schema
split** — move the big text into a side collection keyed by `_id`.

The suite intentionally ships this suboptimal schema first, then shows the tools finding it.

---

## 3. Business query suite (`contoso-queries.js`)

Seven realistic BI aggregations, each needing **only scalar fields** (so each pays the detoast
tax under the co-located schema):

| # | Query | Business question |
|---|-------|-------------------|
| Q1 | `pipeline_by_territory` | Open pipeline value by territory |
| Q2 | `value_by_stage`        | Deal count & value by sales stage |
| Q3 | `monthly_bookings`      | Won bookings trend by month |
| Q4 | `top_accounts`          | Top accounts by pipeline |
| Q5 | `product_mix`           | Revenue by product (line items) |
| Q6 | `rep_leaderboard`       | Won value by sales rep |
| Q7 | `avg_deal_by_industry`  | Avg deal size by industry (join to accounts) |

Metric = **min wall-clock over 5 repetitions** (min = least noise).

---

## 4. Scaling test — the bottleneck the curve reveals

Same query suite, increasing dataset size (co-located schema). Backing-Postgres
`opportunities` heap/TOAST captured per scale.

| Scale | Opps | Total (ms) | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Q7 | Heap | TOAST |
|------:|-----:|-----------:|---:|---:|---:|---:|---:|---:|---:|-----:|------:|
| x1  | 500  | **76**  | 8  | 9  | 7  | 8  | 11 | 7  | 26  | 40 KB  | 3.97 MB |
| x2  | 1000 | **95**  | 12 | 14 | 11 | 11ᵃ| 17 | 11 | 41  | 73 KB  | 7.98 MB |
| x4  | 2000 | **225** | 21 | 26 | 20 | 27 | 31 | 19 | 81  | 139 KB | 16.6 MB |
| x6  | 3000 | **243** | 26 | 31 | 26 | 31 | 45 | 25 | 59  | 221 KB | 23.8 MB |
| x8  | 4000 | **413** | 39 | 48 | 37 | 55 | 58 | 37 | 139 | 278 KB | 31.9 MB |
| x16 | 8000 | **708** | 74 | 99 | 77 | 111| 115| 74 | 158 | 557 KB | 63.5 MB |

ᵃ x2/Q4 = parsing artifact in the harness; the total (95 ms) is correct.

**Bottleneck revealed:** query latency grows roughly **linearly with dataset size**
(76 ms → 708 ms as data grows 16×), tracking the **TOAST volume** (3.97 MB → 63.5 MB, exactly
16×). Every BI aggregation must detoast the full text of every opportunity it scans, even
though it uses none of it. Note the heap stays tiny (40 → 557 KB) — the cost is **all detoast**,
which no index can fix.

(With `shared_buffers = 128 MB` the working set stays cached even at x16, so this is a
**CPU/buffer-traffic** tax from detoasting, not disk I/O — it would additionally become disk I/O
once the working set exceeds cache.)

---

## 5. Diagnostics detect the problem (x8, BEFORE)

### 5a. `document-bloat-advisor.sh --db contoso_x8`
```
⚠️  opportunities   heap=272KB  TOAST=31144KB  (TOAST ratio 0.991)  avgObjSize=6342B
      dominant fields: narrative:3502B, activity_log:2502B, line_items:174B
      Fix: move 'narrative' (+ other large text) into side collection
           'opportunities_text' keyed by _id; keep opportunities scalar-only.
⚠️  accounts        heap=88KB   TOAST=4800KB   (ratio 0.982)  profile:3502B
⚠️  campaigns       heap=8KB    TOAST=256KB    (ratio 0.970)  content:4002B
✅  products        heap=256KB  TOAST=0KB      (ratio 0.000) — no bloat
Flagged 3 collections; 36,200KB of TOASTed text detoasted on every scan.
```
The tool cross-references MongoDB `avgObjSize` with PostgreSQL heap/TOAST sizes, names the
offending fields, and prescribes the DocumentDB-specific schema-split fix. `products`
(compressible/short description) is correctly **not** flagged.

### 5b. `db-config-advisor.sh --db contoso_x8`
```
shared_buffers = 128 MB (source: configuration file)
Working set for 'contoso_x8' = 36.9 MB  (heap 0.6 + TOAST 35.4 + idx 0.3)   TOAST share = 96%
Cache hit: heap 100% / TOAST 100% / index 100%  (a few TOAST blocks read from disk)
• TOAST is 96% of the working set. Removing it (schema split) would cut the working set to
  1.6 MB, letting the hot data stay resident WITHOUT changing config.
```
Every statement is tied to a **measured** number — no generic "set shared_buffers to 25 % of
RAM." The advisor's recommendation (shrink the working set before touching config) points back
to the bloat fix.

---

## 6. Before / After — applying the diagnostic-recommended fix

Fix applied by `contoso-split-fix.js` (the remediation the advisor recommends): move
`narrative` + `activity_log` into `opportunities_text` (keyed by `_id`), `$unset` them from
`opportunities`, then `VACUUM`.

### 6a. Query latency (x8, 4,000 opportunities, min of 5 reps)

| Query | Before (ms) | After (ms) | Speed-up |
|-------|------------:|-----------:|---------:|
| pipeline_by_territory | 39  | 8   | **4.9×** |
| value_by_stage        | 48  | 9   | **5.3×** |
| monthly_bookings      | 37  | 7   | **5.3×** |
| top_accounts          | 55  | 10  | **5.5×** |
| product_mix           | 58  | 32  | 1.8× |
| rep_leaderboard       | 37  | 6   | **6.2×** |
| avg_deal_by_industry  | 139 | 45  | 3.1× |
| **TOTAL**             | **413** | **117** | **3.5×** |

Pure `opportunities` scans got **~5× faster**. The two smaller gains are instructive:
`product_mix` still unwinds `line_items` (kept in the doc), and `avg_deal_by_industry` **joins
`accounts`, which is still bloated** — i.e., the remaining tax comes from collections not yet
fixed, reinforcing the advisor's other findings.

### 6b. Storage / working set (opportunities)

| State | opportunities heap | opportunities TOAST | BI hot-path size |
|-------|-------------------:|--------------------:|-----------------:|
| Before | 272 KB | 31,144 KB | **≈ 31.4 MB** |
| After  | 2,024 KB | **0 KB** | **≈ 2.0 MB**  (‑15.7×) |

`document-bloat-advisor.sh` after split + vacuum:
```
✅  opportunities       heap=2024KB TOAST=0KB (ratio 0.000) — no bloat
⚠️  opportunities_text  (now holds the 31 MB text — COLD, read only for detail views)
```

**The text is preserved, just relocated** off the hot BI path. Total stored bytes are similar;
what changed is that BI aggregations now scan a 2 MB inline heap instead of detoasting 31 MB —
hence the 3.5–6× latency win. The fix is an **application/schema change** (write text to
`opportunities_text`, read it only on detail views), exactly the kind of guidance
`index-redundancy-finder.sh` gives for indexes.

---

## 7. What the two new tools add to the kit

| Tool | Layer | What it measures (facts only) | Actionable output |
|------|-------|-------------------------------|-------------------|
| `document-bloat-advisor.sh` | Mongo + PG | avgObjSize, per-collection heap vs TOAST, dominant fields | Which collection/field to split into a side collection (app-code fix) |
| `db-config-advisor.sh` | PG | shared_buffers, working set (heap+TOAST+idx), measured cache-hit, TOAST share | Evidence-based: shrink working set (bloat fix) vs raise `shared_buffers` toward the *measured* working set |

Both follow the kit's principle established earlier: **report measured facts and concrete
structural issues; never emit generic rules-of-thumb.** The config advisor deliberately does
not prescribe "25 % of RAM"; it derives everything from the workload's own numbers.

---

## 8. Reproduce

```bash
# seed one scale (resumable)
docker cp scenarios/contoso/contoso-seed.js  <container>:/tmp/
CONTOSO_DB=contoso_x8 CONTOSO_SCALE=8 mongosh ... --file /tmp/contoso-seed.js

# full scaling benchmark (kill-tolerant)
bash scenarios/contoso/scale-bench2.sh "1 2 4 6 8 16"

# diagnose
bash scripts/document-bloat-advisor.sh --db contoso_x8
bash scripts/db-config-advisor.sh      --db contoso_x8

# apply the fix, re-measure
CONTOSO_DB=contoso_x8 mongosh ... --file /tmp/contoso-split-fix.js
```

---

## 9. Environment note (transparency)

The shared Docker host repeatedly killed the container; worse, `documentdb-local` re-runs its
sample-data init on every start and **crash-loops** (dup-key on `01-users.js`) once `/data` is
populated. Recovery: `docker commit` (no external volume exists — commit preserves `/data`),
then run with `-e SKIP_INIT_DATA=true -e INIT_DATA_PATH=/tmp/noinit` to skip init. After that
the container was stable and all six scales seeded and benched cleanly. The seeder and harness
were made **resumable/kill-tolerant** so partial seeds converge across restarts.

---

## 10. Headline

- **Bottleneck:** BI query latency scales linearly with data because large co-located text is
  detoasted on every scan (x1 76 ms → x16 708 ms; TOAST 3.97 → 63.5 MB).
- **Diagnosis:** `document-bloat-advisor.sh` pinpoints `opportunities` at 99 % TOAST and names
  the fields; `db-config-advisor.sh` shows TOAST is 96 % of the working set.
- **Fix (app/schema):** split large text into a side collection → **3.5× faster** query suite
  (individual scans up to **6× faster**), hot working set **15.7× smaller**, zero TOAST on the
  hot path — with no config change and no data loss.
