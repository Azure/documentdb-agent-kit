# Quick Start: Find & Fix a Slow Query on Azure DocumentDB

**Time: ~10 minutes.** In this guide you'll run Azure DocumentDB locally, load a
sample store dataset, ask your AI coding assistant *why a query is slow*, apply the
one-line fix it recommends, and watch the same query go from scanning **all 50,000
documents** to a **tiny index lookup** of just the rows that match — with no
application code change.

You don't need to know anything about the internals. If you have Docker and an AI
coding assistant, you can follow along by copy-paste.

---

## What is this?

The **Azure DocumentDB Agent Kit** is a set of *skills* you add to your AI coding
assistant (Claude Code, Cursor, GitHub Copilot CLI, Gemini CLI, VS Code, …). Once
installed, your assistant knows how to diagnose and optimize
[Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/) (the managed,
MongoDB-compatible database) — reading `explain()` output, designing indexes, and
more.

Install the skills (one time):

```bash
npx skills add Azure/documentdb-agent-kit
```

For the sample data and the ready-made test used below, also grab the repo:

```bash
git clone https://github.com/Azure/documentdb-agent-kit
cd documentdb-agent-kit
```

> **Preview:** DocumentDB agent-kit is in public preview; details may
> change. No production SLA.

---

## Step 1 — Run DocumentDB locally

First pick a password for your local container. Every command in this guide reads
it from `DB_PASSWORD`, so you only type it once (choose anything — this container
is a throwaway on your own machine):

```bash
export DB_PASSWORD='<choose-a-password>'
```

> Keep it in your shell for the whole walkthrough. If you open a **new terminal**,
> re-run that `export` before continuing.

```bash
docker run -d --name documentdb-local \
  -e USERNAME=docdbadmin -e PASSWORD="$DB_PASSWORD" \
  ghcr.io/microsoft/documentdb/documentdb-local:latest
```

Add a Mongo shell to the container (the preview image ships without one, and the
sample-data loader uses it):

```bash
docker exec -u root documentdb-local bash -lc '
  cd /tmp && wget -q https://downloads.mongodb.com/compass/mongosh-2.3.8-linux-x64.tgz -O m.tgz &&
  tar xzf m.tgz && cp mongosh-2.3.8-linux-x64/bin/mongosh /usr/local/bin/ &&
  cp mongosh-2.3.8-linux-x64/bin/mongosh_crypt_v1.so /usr/local/lib/ 2>/dev/null; mongosh --version'
```

## Step 2 — Load the sample data

This seeds a realistic store database (`ecommerce`) — **50,000 orders**,
customers, products, and more. It takes about a minute.

```bash
bash scenarios/ecommerce/seed.sh
```

The `orders` collection starts with **no indexes** (other than the default `_id`)
— exactly the situation that makes queries slow as data grows.

---

## Step 3 — Open a Mongo shell

The queries in the next steps are **MongoDB commands** — you run them at an
interactive `mongosh` prompt connected to your local database. Open one now:

```bash
docker exec -it -u documentdb documentdb-local mongosh "localhost:10260/ecommerce" \
  -u docdbadmin -p "$DB_PASSWORD" --authenticationMechanism SCRAM-SHA-256 --tls \
  --tlsAllowInvalidCertificates
```

You'll land at a prompt like this — every `db.orders.…` command below is typed here:

```text
[direct: mongos] ecommerce>
```

> Type `exit` (or press `Ctrl-D`) to leave the shell. Already using the DocumentDB
> **MCP server** with your AI assistant? You can skip this shell — the assistant
> runs the same commands for you.

---

## Step 4 — Ask your assistant why a query is slow

Here's a perfectly reasonable query — find one customer's shipped orders since the
start of the year, newest first.

The sample data is generated **randomly**, so first grab a customer that actually
has several shipped orders in *your* copy (run this at the `ecommerce>` prompt):

```javascript
db.orders.aggregate([
  { $match: { status: "shipped", created_at: { $gte: ISODate("2024-01-01") } } },
  { $group: { _id: "$customer_id", n: { $sum: 1 } } },
  { $sort: { n: -1 } }, { $limit: 1 }
])
```

That prints the busiest customer (for example `CUST_004087`). Use that id in the
query below:

```javascript
db.orders.find({
  status: "shipped",
  customer_id: "CUST_004087",          // ← use the id printed above
  created_at: { $gte: ISODate("2024-01-01") }
}).sort({ created_at: -1 })
```

Paste this prompt to your AI assistant — swap in your customer id (the kit's skill
will pick it up). Give it the surrounding context too, so it can inspect the
database itself instead of guessing:

```text
Why is this query slow on my Azure DocumentDB database, and how do I fix it?

  db.orders.find({
    status: "shipped",
    customer_id: "CUST_004087",
    created_at: { $gte: ISODate("2024-01-01") }
  }).sort({ created_at: -1 })

Context:
- Azure DocumentDB (MongoDB-compatible) running locally in Docker,
  container "documentdb-local", database "ecommerce", collection "orders".
- ~50,000 orders. The only index is the default _id — I haven't added any.
- Each order has: order_id, customer_id, status (pending/confirmed/shipped/
  delivered/cancelled), payment_method, created_at, updated_at, shipping_city,
  total_amount.
- If you don't have a database connection, run commands through the shell
  (the password is in my DB_PASSWORD environment variable):
  docker exec -u documentdb documentdb-local mongosh "localhost:10260/ecommerce" \
    -u docdbadmin -p "$DB_PASSWORD" --authenticationMechanism SCRAM-SHA-256 --tls \
    --tlsAllowInvalidCertificates --quiet --eval '<command>'

Please run explain("executionStats"), tell me what the plan is doing, and
recommend an index. Ask me before creating anything.
```

> **Why the extra context?** Without it the assistant has to guess which database
> you mean and has no way to run `explain()` — so it can only give generic advice.
> With it, it inspects *your* data and gives a specific answer. If you've set up
> the [DocumentDB MCP server](https://github.com/microsoft/documentdb-mcp), the
> assistant already has a connection and you can drop the `docker exec` line.

Your assistant will run `explain("executionStats")` and spot the problem: a
**collection scan** (`COLLSCAN`) — the database reads **every one** of the 50,000
documents just to return the handful (about 10) that match.

> **Prefer to look yourself?** At the `ecommerce>` prompt from Step 3, run the
> same query with `.explain("executionStats")` appended:
>
> ```javascript
> db.orders.find({ status: "shipped", customer_id: "CUST_004087", created_at: { $gte: ISODate("2024-01-01") } }).sort({ created_at: -1 }).explain("executionStats")
> ```
>
> ⚠️ **Read the scan stage, not the summary.** The top-line time can look tiny (a
> few milliseconds) even during a full scan — look at the `COLLSCAN` stage, where
> `totalDocsExamined` is **50,000**.

*(No assistant handy? The kit also ships a deterministic router that names the
right skill for a question — `bash knowledge-base/kb-route.sh "why is this query slow and how do I index it"`.)*

---

## Step 5 — Apply the recommended fix

The skill recommends a single **compound index**, ordered by the **ESR rule**
(Equality → Sort → Range), with the most selective field first. At the
`ecommerce>` prompt, run:

```javascript
db.orders.createIndex({ customer_id: 1, status: 1, created_at: -1 })
```

(Your assistant will ask for approval before creating it.)

> **Not in the shell?** You can run it from your host in one line instead:
>
> ```bash
> docker exec -u documentdb documentdb-local mongosh "localhost:10260/ecommerce" \
>   -u docdbadmin -p "$DB_PASSWORD" --authenticationMechanism SCRAM-SHA-256 --tls \
>   --tlsAllowInvalidCertificates --quiet \
>   --eval 'db.orders.createIndex({ customer_id: 1, status: 1, created_at: -1 })'
> ```

## Step 6 — See the improvement

Run the query with `.explain("executionStats")` again at the `ecommerce>` prompt:

```javascript
db.orders.find({
  status: "shipped",
  customer_id: "CUST_004087",
  created_at: { $gte: ISODate("2024-01-01") }
}).sort({ created_at: -1 }).explain("executionStats")
```

The `COLLSCAN` is gone, replaced by an **index scan** (`IXSCAN`) that examines
only the rows it needs:

| | Before (no index) | After (ESR index) |
|---|---|---|
| Plan | `COLLSCAN` (full scan) | `IXSCAN` (index scan) |
| Documents/keys examined | **50,000** (every document) | **only the matching rows** (≈10) |
| Rows returned | ≈10 | ≈10 |

**Thousands of times less work per query** (≈5,000× in the example above). Same
result, a fraction of the resources — which means more headroom to scale without
adding infrastructure.

> **Your exact numbers will differ** — the sample data is generated randomly, so
> the number of matching orders (and which customer is busiest) changes each time
> you seed. What always holds is the pattern: a full **50,000-document scan**
> collapses to a **tiny index lookup** of just the rows that match.

---

## Try a few more (one command)

The kit includes a ready-made test that runs several *before/after* comparisons
for you and prints the results:

```bash
# uses the same DB_PASSWORD you exported in Step 1
bash scenarios/ecommerce/query-perf-skill-test.sh
```

You'll see the same pattern across different query shapes — the size of the win
depends on how *selective* the filter is (the **before → after** figures below are
from one example run; your exact counts will vary with the random sample data, but
the `order_id` lookup is always a unique 50,000 → 1):

| Ask your assistant… | Recommended index | Examined: before → after |
|---|---|---|
| "Does this query use an index or a collection scan?" (`find` by `order_id`) | `{ order_id: 1 }` | 50,000 → **1** |
| "Optimize `find({status, shipping_city}).sort({created_at})`" | `{ status: 1, shipping_city: 1, created_at: -1 }` | 50,000 → **~1,000** |
| "Tune the flagship `find({status, customer_id, created_at}).sort()`" | `{ customer_id: 1, status: 1, created_at: -1 }` | 50,000 → **~10** |
| "Which compound index for `find({status, total_amount:{$gt}}).sort({created_at})`?" | `{ status: 1, created_at: -1, total_amount: 1 }` | 50,000 → **~8,900** |

*(The test creates each index, measures, and drops it again, so your `orders`
collection is left exactly as it started.)*

---

## What you get on managed Azure DocumentDB

This local image demonstrates the **biggest** win — turning a full scan into an
index scan. Managed **Azure DocumentDB** goes further with two optimizations that
are enabled there but not in the local preview image:

- **Index-backed sort** — the index returns rows already in order, removing the
  in-memory sort step.
- **Covered queries** — when the index contains every field the query needs, the
  database never touches the documents at all.

So on Azure the same query gets *even* faster. Learn more:
[Query Performance Tuning Guide](https://devblogs.microsoft.com/documentdb/query-performance-tuning-guide/) ·
[How to read explain output](https://learn.microsoft.com/azure/documentdb/how-to-read-explain-output).

---

## Clean up

```bash
docker rm -f documentdb-local
```

## Where to next

- **Ask your assistant** to review the indexes on your own collections, or to
  explain a slow query from your app — the same skills apply.
- **Find slow queries in production:** on Azure, route Diagnostic Logs to a Log
  Analytics workspace and rank operations in the `VCoreMongoRequests` table by
  `DurationMs`, then bring the worst offender back to your assistant.
