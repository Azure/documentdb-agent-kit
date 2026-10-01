// fixture.js — remediation effect
//
// Seeds a collection with a REAL, measurable performance defect: a moderately
// large `orders` collection with NO secondary indexes, so every filtered query
// degenerates into a collection scan that reads the whole table to return a
// handful of rows.
//
// The point of this scenario is not to prove that indexes work — everyone knows
// that. It is to prove that THE KIT'S OWN ADVICE, applied literally, produces a
// measurable improvement, and that the kit's tools then confirm the fix. So the
// fixture must contain a defect the diagnostic scripts actually detect.
//
// Deterministic by construction: no Math.random() anywhere, so the same seed
// yields the same collection every time and the before/after numbers are
// reproducible.

db.orders.drop();

var STATUSES = ["shipped", "pending", "cancelled"];
var N = 20000;

var bulk = [];
for (var i = 1; i <= N; i++) {
    bulk.push({
        order_id: i,
        // 2000 distinct customers over 20000 orders => 10 orders each.
        // Selective enough that a collection scan is obviously wasteful:
        // 20000 documents read to return 10.
        customer_id: "C" + (i % 2000),
        status: STATUSES[i % 3],
        amount: (i % 500) + 10,
        region: ["emea", "amer", "apac"][i % 3]
    });
    if (bulk.length === 5000) { db.orders.insertMany(bulk); bulk = []; }
}
if (bulk.length) db.orders.insertMany(bulk);

// Deliberately NO secondary indexes: _id only. This is the "before" state.

print("FIXTURE_READY remediation-effect");
print("  orders: " + db.orders.countDocuments() + " docs, " +
      db.orders.getIndexes().length + " index(es)");
