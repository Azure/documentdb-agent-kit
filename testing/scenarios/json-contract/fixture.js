// fixture.js — json-contract (shape guard for every script's --json output)
//
// Seeds a small, generic DB with enough structure that all five diagnostic
// scripts produce a fully-populated JSON result:
//   * customers / orders  -> a foreign-key relationship + a prefix-redundant
//                            index pair on orders
//   * documents           -> large VARIED text (low compressibility) so the
//                            column is pushed to PostgreSQL TOAST, exercising
//                            the large-document advisor
//
// This is a SHAPE fixture: the tests assert JSON validity + structure, never
// specific finding counts, so the data does not need to be deterministic.

var ADVERSARIAL_COLLECTION =
    "safe;db.getCollection('diagnostic_sentinel').drop();db.safe";

[
    "customers",
    "orders",
    "documents",
    "safe",
    "diagnostic_sentinel",
    ADVERSARIAL_COLLECTION
].forEach(function (c) {
    try { db[c].drop(); } catch (e) {}
});

// ---- customers (FK target) ----
var bulk = [];
for (var i = 1; i <= 200; i++) {
    bulk.push({ customer_id: i, email: "c" + i + "@ex.com", country: ["US", "DE", "JP"][i % 3] });
}
db.customers.insertMany(bulk);
db.customers.createIndex({ email: 1 }, { unique: true });

// ---- orders (FK source + prefix-redundant index pair) ----
bulk = [];
for (var i = 1; i <= 300; i++) {
    bulk.push({
        order_id: i,
        customer_id: (i % 200) + 1,
        status: ["pending", "paid", "shipped"][i % 3],
        created_at: new Date(2024, i % 12, (i % 28) + 1)
    });
}
db.orders.insertMany(bulk);
db.orders.createIndex({ customer_id: 1 });            // prefix ...
db.orders.createIndex({ customer_id: 1, status: 1 }); // ... of this -> redundant

// ---- documents: big VARIED text co-located -> TOAST (large-document advisor) ----
var CH = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789     .,;";
var POOL = "";
while (POOL.length < 24000) POOL += CH[Math.floor(Math.random() * CH.length)];
function txt(n) { var o = Math.floor(Math.random() * (POOL.length - n - 1)); return POOL.substr(o, n); }
bulk = [];
for (var i = 1; i <= 120; i++) {
    bulk.push({ _id: i, kind: "note", amount: i * 10, blob: txt(6000) });
}
db.documents.insertMany(bulk);
db.safe.insertOne({ _id: 1, marker: "safe" });
db.diagnostic_sentinel.insertOne({ _id: 1, marker: "must-survive" });
db.getCollection(ADVERSARIAL_COLLECTION).insertMany(bulk);

print("FIXTURE_READY json-contract");
db.getCollectionNames().sort().forEach(function (c) {
    print("  " + c + ": " + db[c].countDocuments() + " docs, " + db[c].getIndexes().length + " indexes");
});
