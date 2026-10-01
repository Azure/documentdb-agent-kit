// fixture.js — ecommerce-missing-index
// Seeds a collection that is queried on an UNINDEXED field so perf-advisor.sh
// flags a COLLSCAN. A second, properly-indexed collection is included so the
// scenario also proves perf-advisor does NOT flag well-indexed access.
//
// Planted issue (answer key — see expected-findings.yaml):
//   events.event_type / events.device_id : no supporting index -> COLLSCAN

["events", "products", "escaped_values"].forEach(function (c) {
    try { db[c].drop(); } catch (e) {}
});

// ---- events: NO secondary indexes -> queries on these fields must COLLSCAN ----
var bulk = [];
for (var i = 1; i <= 2000; i++) {
    bulk.push({
        event_id: i,
        device_id: "dev-" + (i % 200),
        event_type: ["click", "view", "purchase", "error"][i % 4],
        ts: new Date(2024, (i % 12), (i % 28) + 1)
    });
}
db.events.insertMany(bulk);
// (intentionally NO createIndex on events)

// ---- products: properly indexed (control) ----
bulk = [];
for (var i = 1; i <= 500; i++) {
    bulk.push({
        sku: "SKU-" + i,
        category: ["a", "b", "c"][i % 3],
        price: (i % 100) + 1
    });
}
db.products.insertMany(bulk);
db.products.createIndex({ sku: 1 });
db.products.createIndex({ category: 1 });
db.products.createIndex({ price: 1 });

// ---- escaped_values: prove probe filters do not concatenate JSON strings ----
// Both the field name and sampled value contain JSON-significant characters.
// Building `JSON.parse("{\"" + field + ... )` throws before testQuery runs and
// used to make perf-advisor silently lose every Mongo-layer finding.
bulk = [];
for (var i = 1; i <= 20; i++) {
    var doc = { _id: i };
    doc['path"key\\segment'] =
        i === 1 ? 'say "hello" \\ root' : "ordinary-" + i;
    bulk.push(doc);
}
db.escaped_values.insertMany(bulk);
// (intentionally NO secondary indexes)

print("FIXTURE_READY missing-index");
print("  events: " + db.events.countDocuments() + " docs, "
      + db.events.getIndexes().length + " indexes");
print("  products: " + db.products.countDocuments() + " docs, "
      + db.products.getIndexes().length + " indexes");
print("  escaped_values: " + db.escaped_values.countDocuments() + " docs, "
      + db.escaped_values.getIndexes().length + " indexes");
