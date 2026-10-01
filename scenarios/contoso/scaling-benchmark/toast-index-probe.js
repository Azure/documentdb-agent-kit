// toast-index-probe.js — measure the detoast tax for ONE query under whatever
// index currently exists on opportunities. Emits a single JSON line so a shell
// driver can sweep a matrix of {index config} x {schema state}.
//
// The key evidence is NOT just wall-clock ms (noisy) but the PostgreSQL block
// traffic the executor reports: numBlocksFromCache + numBlocksFromDisk. Under
// the co-located schema every matched document is detoasted, so a query that
// touches only scalar fields still reads the entire TOAST chain — the block
// count explodes. After the schema split the same query reads far fewer blocks.
//
// Env:
//   CONTOSO_DB   database (default contoso_x16)
//   QUERY        which query: "selective" (default) | "fullscan"
//   QUERY_REPS   timed reps, report MIN ms (default 7)
//   IDX_LABEL    label of the current index config (passed through to output)

var DB    = process.env.CONTOSO_DB || "contoso_x16";
var QUERY = process.env.QUERY || "selective";
var REPS  = parseInt(process.env.QUERY_REPS || "7");
var LABEL = process.env.IDX_LABEL || "unknown";
var d = db.getSiblingDB(DB);

// The two aggregations both read ONLY scalar fields (never narrative/activity_log).
function pipeline() {
    if (QUERY === "fullscan") {
        // no $match -> every document participates -> detoast on 100% of docs
        return [
            { $group: { _id: "$sales_stage", n: { $sum: 1 }, value: { $sum: "$est_value" } } },
            { $sort: { value: -1 } }
        ];
    }
    // selective: ~1/3 of docs (state:open) -> an index on state can prune keys,
    // but every surviving doc is still FETCHed and detoasted (co-located schema).
    return [
        { $match: { state: "open" } },
        { $group: { _id: "$territory_id", pipeline: { $sum: "$est_value" }, deals: { $sum: 1 } } },
        { $sort: { pipeline: -1 } }
    ];
}

function longVal(x) { return (x && typeof x === "object" && "low" in x) ? x.low : x; }

// ── explain: pull plan stage + docs examined + PG block traffic ─────────────
var e = d.opportunities.explain("executionStats").aggregate(pipeline());
var cur = null;
(e.stages || []).forEach(function (s) { if (s.$cursor) cur = s.$cursor; });

var stage = "?", docsExamined = -1, blocksCache = -1, blocksDisk = -1, planMs = -1, idxName = "";
if (cur) {
    var wp = cur.queryPlanner && cur.queryPlanner.winningPlan;
    if (wp) {
        stage = wp.stage || "?";
        // index name may live on this stage or a child inputStage
        var node = wp;
        while (node && !idxName) {
            if (node.indexName) idxName = node.indexName;
            node = node.inputStage;
        }
    }
    var es = cur.executionStats;
    if (es) {
        docsExamined = longVal(es.totalDocsExamined);
        planMs = longVal(es.executionTimeMillis);
        var exec = es.executionStages;
        if (exec) {
            blocksCache = longVal(exec.numBlocksFromCache);
            blocksDisk  = longVal(exec.numBlocksFromDisk);
        }
    }
}

// ── timed run: report MIN wall-clock ms over REPS ───────────────────────────
var best = Infinity, rows = 0;
for (var r = 0; r < REPS; r++) {
    var t = Date.now();
    rows = d.opportunities.aggregate(pipeline()).toArray().length;
    var ms = Date.now() - t;
    if (ms < best) best = ms;
}

var blocksTotal = (blocksCache < 0 ? 0 : blocksCache) + (blocksDisk < 0 ? 0 : blocksDisk);
print("IDXRESULT " + JSON.stringify({
    db: DB, query: QUERY, idx: LABEL, index_used: idxName || stage,
    stage: stage, docs_examined: docsExamined,
    blocks_cache: blocksCache, blocks_disk: blocksDisk, blocks_total: blocksTotal,
    blocks_mib: Math.round(blocksTotal * 8 / 1024 * 10) / 10,
    plan_ms: planMs, min_ms: best, rows: rows,
    opps: d.opportunities.countDocuments()
}));
