// fixture.js — index-redundancy diagnosis
//
// Plants a KNOWN, unambiguous set of redundant indexes so the correct answer is
// a fact, not a judgement — which is what lets parity be graded structurally
// rather than by an LLM.
//
// Deterministic by construction: no Math.random() anywhere. Every run of both
// arms sees byte-identical data, so a cost difference cannot be a data
// difference.
//
// Planted redundancies (and nothing else):
//   accounts.tenant_id_1        prefix of tenant_id_1_status_1   -> REDUNDANT
//   accounts.email_1            duplicate of email_unique        -> REDUNDANT
// Deliberately NOT redundant, as controls against over-reporting:
//   accounts.tenant_id_1_status_1  the covering compound index
//   accounts.email_unique          the unique constraint
//   orders.customer_id_1           sole index on another collection

db.accounts.drop();
db.orders.drop();

var bulk = [];
for (var i = 1; i <= 2000; i++) {
    bulk.push({
        account_id: i,
        email: "user" + i + "@example.test",
        tenant_id: (i % 25) + 1,
        status: ["active", "inactive", "pending"][i % 3]
    });
    if (bulk.length === 1000) { db.accounts.insertMany(bulk); bulk = []; }
}
if (bulk.length) db.accounts.insertMany(bulk);

db.accounts.createIndex({ tenant_id: 1 });                              // redundant
db.accounts.createIndex({ tenant_id: 1, status: 1 });                   // keep
db.accounts.createIndex({ email: 1 });                                  // redundant
db.accounts.createIndex({ email: 1 }, { unique: true, name: "email_unique" });

bulk = [];
for (var i = 1; i <= 1000; i++) {
    bulk.push({ order_id: i, customer_id: "C" + (i % 200), amount: (i % 90) + 10 });
}
db.orders.insertMany(bulk);
db.orders.createIndex({ customer_id: 1 });                              // keep

print("FIXTURE_READY index-redundancy-diagnosis");
db.getCollectionNames().sort().forEach(function (c) {
    print("  " + c + ": " + db[c].countDocuments() + " docs, " +
          db[c].getIndexes().length + " indexes");
});
