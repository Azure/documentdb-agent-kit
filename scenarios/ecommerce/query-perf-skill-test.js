// query-perf-skill-test.js — before/after query-performance harness for the
// "Query Performance Tuning Guide" skills, run against the seeded `ecommerce`
// dataset (orders: 50,000 docs, no secondary index by default).
//
// For each skill it: (1) drops every non-_id index on `orders` to force the
// COLLSCAN baseline, (2) measures the slow query with explain("executionStats"),
// (3) creates the skill's recommended index, (4) re-measures, then drops it.
//
// It reports the honest "work" metric the article tells you to read — the
// documents/keys examined AT THE SCAN STAGE (not the misleading top-line count) —
// plus the winning plan shape and a min-of-5 executionTimeMillis.
//
// Run via: bash scenarios/ecommerce/query-perf-skill-test.sh
// (or: mongosh <conn>/ecommerce --file query-perf-skill-test.js)

const COLL = "orders";
const RUNS = 5;

// ── helpers ─────────────────────────────────────────────────────────────────
function N(x) {                         // DocumentDB returns Long as {low,high}
  if (x && typeof x === "object" && "low" in x) return x.low;
  return typeof x === "number" ? x : 0;
}
function stagesOf(root) {                // flatten the inputStage chain
  const out = [];
  for (let s = root; s; s = s.inputStage) out.push(s);
  return out;
}
function measure(filter, sort, projection) {
  let best = null, tMin = Infinity;
  for (let i = 0; i < RUNS; i++) {
    let cur = db[COLL].find(filter, projection || {});
    if (sort) cur = cur.sort(sort);
    const e = cur.explain("executionStats");
    const es = e.executionStats;
    const chain = stagesOf(es.executionStages);
    const scan = chain[chain.length - 1];               // deepest stage
    const t = N(es.executionTimeMillis);
    if (t < tMin) tMin = t;
    if (!best) {
      const fetch = chain.find(s => s.stage === "FETCH");
      best = {
        planTop: es.executionStages.stage,
        scanStage: scan.stage,
        scanIndex: scan.indexName || null,
        // COLLSCAN reports work as totalDocsExamined; IXSCAN as totalKeysExamined
        scanExamined: scan.stage === "COLLSCAN" ? N(scan.totalDocsExamined)
                                                : N(scan.totalKeysExamined),
        scanExaminedField: scan.stage === "COLLSCAN" ? "docsExamined" : "keysExamined",
        docsFetched: fetch ? N(fetch.totalDocsExamined) : 0,
        hasSort: chain.some(s => s.stage === "SORT"),
        hasFetch: !!fetch,
        topDocsExamined: N(es.totalDocsExamined),        // the misleading top-line
        nReturned: N(es.nReturned),
      };
    }
  }
  best.timeMsMin = tMin;
  return best;
}
function dropSecondary() {
  db[COLL].getIndexes().filter(i => i.name !== "_id_")
          .forEach(i => db[COLL].dropIndex(i.name));
}
function fmt(m) {
  const sort = m.hasSort ? " +SORT" : "";
  const fetch = m.hasFetch ? " +FETCH" : "";
  return `${m.scanStage}${m.scanIndex ? "(" + m.scanIndex + ")" : ""}` +
         `  ${m.scanExaminedField}=${m.scanExamined}${sort}${fetch}` +
         `  nReturned=${m.nReturned}  time=${m.timeMsMin}ms  (top docsExamined=${m.topDocsExamined})`;
}

// ── the four skill test cases ────────────────────────────────────────────────
const TESTS = [
  {
    skill: "documentdb-query-optimizer",
    rule: "explain-plan verification (merged from the former query-optimization skill)",
    point: "explain() literacy: a COLLSCAN becomes an IXSCAN once an index supports the filter",
    trigger: "use explain to check whether this query uses an index or does a collection scan",
    filter: { order_id: "ORD_012345" },
    sort: null,
    index: { order_id: 1 },
  },
  {
    skill: "documentdb-query-optimizer",
    rule: "(standalone skill)",
    point: "recommend a compound index for a specific slow query (two equality fields + sort)",
    trigger: "optimize this query and recommend an index",
    filter: { status: "shipped", shipping_city: "Seattle" },
    sort: { created_at: -1 },
    index: { status: 1, shipping_city: 1, created_at: -1 },
  },
  {
    skill: "documentdb-query-performance-tuning",
    rule: "(standalone skill) — the article's flagship query",
    point: "full ESR compound index, most-selective equality first; + covered-query variant",
    trigger: "how do I read the explain output and apply the ESR rule to tune this query",
    filter: { status: "shipped", customer_id: "CUST_004087", created_at: { $gte: ISODate("2024-01-01") } },
    sort: { created_at: -1 },
    index: { customer_id: 1, status: 1, created_at: -1 },
    covered: { _id: 0, customer_id: 1, status: 1, created_at: 1 },
  },
  {
    skill: "documentdb-indexing",
    rule: "index-compound-esr",
    point: "ESR with a range predicate: Equality, then Sort, then Range LAST",
    trigger: "which compound index should I design for this filter, sort, and range query",
    filter: { status: "shipped", total_amount: { $gt: 500 } },
    sort: { created_at: -1 },
    index: { status: 1, created_at: -1, total_amount: 1 },
  },
];

// ── run ──────────────────────────────────────────────────────────────────────
print("=".repeat(78));
print("  Query-Performance Skill Test — dataset: " + db.getName() + "." + COLL +
      " (" + db[COLL].countDocuments() + " docs)");
print("=".repeat(78));

const summary = [];
for (const t of TESTS) {
  dropSecondary();
  const before = measure(t.filter, t.sort);
  const idxName = db[COLL].createIndex(t.index);
  sleep(500);
  const after = measure(t.filter, t.sort);
  let covered = null;
  if (t.covered) covered = measure(t.filter, t.sort, t.covered);
  dropSecondary();

  print("\n### " + t.skill + "   [" + t.rule + "]");
  print("  goal    : " + t.point);
  print("  trigger : \"" + t.trigger + "\"");
  print("  query   : db.orders.find(" + JSON.stringify(t.filter) +
        (t.sort ? ").sort(" + JSON.stringify(t.sort) : "") + ")");
  print("  index   : db.orders.createIndex(" + JSON.stringify(t.index) + ")   [" + idxName + "]");
  print("  BEFORE  : " + fmt(before));
  print("  AFTER   : " + fmt(after));
  if (covered) print("  COVERED : " + fmt(covered));
  const reduction = after.scanExamined > 0
    ? (before.scanExamined / after.scanExamined).toFixed(0) + "x fewer examined at the scan"
    : "n/a";
  print("  RESULT  : scan work " + before.scanExamined + " -> " + after.scanExamined +
        " (" + reduction + ")");

  summary.push({
    skill: t.skill, rule: t.rule, trigger: t.trigger,
    filter: t.filter, sort: t.sort, index: t.index, indexName: idxName,
    before, after, covered,
    scanWorkReduction: after.scanExamined > 0 ? before.scanExamined / after.scanExamined : null,
  });
}

print("\n" + "---JSON-START---");
print(JSON.stringify({ dataset: db.getName(), collection: COLL,
                       docCount: db[COLL].countDocuments(), results: summary }, null, 1));
print("---JSON-END---");
