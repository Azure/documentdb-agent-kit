// contoso-probe.js — minimal, survivable timing probe.
// Runs ONE canonical BI query (open pipeline value by territory: full scan +
// $group over opportunities — the query that pays the detoast tax) REPS times
// and prints the MIN wall-clock ms. Sub-second even at large scale, so it
// completes between container cycles in a flaky environment.
// Env: CONTOSO_DB, QUERY_REPS (default 7)
var DB = process.env.CONTOSO_DB || "contoso_x1";
var REPS = parseInt(process.env.QUERY_REPS || "7");
var d = db.getSiblingDB(DB);
var best = Infinity, rows = 0;
for (var r = 0; r < REPS; r++) {
    var t = Date.now();
    rows = d.opportunities.aggregate([
        { $match: { state: "open" } },
        { $group: { _id: "$territory_id", pipeline: { $sum: "$est_value" }, deals: { $sum: 1 } } },
        { $sort: { pipeline: -1 } }
    ]).toArray().length;
    var ms = Date.now() - t;
    if (ms < best) best = ms;
}
print("PROBE " + DB + " min_ms=" + best + " reps=" + REPS + " opps=" + d.opportunities.countDocuments() + " groups=" + rows);
