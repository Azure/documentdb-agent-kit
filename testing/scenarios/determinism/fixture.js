// fixture.js — determinism
// Seeds a database that makes EVERY diagnostic script produce NON-EMPTY output.
//
// That matters: a script trivially looks "deterministic" when it finds nothing
// (empty output is identical every run). This fixture plants real findings for
// each script so the determinism assertion is meaningful:
//
//   index-redundancy-finder  <- redundant / duplicate / reverse-variant indexes
//   data-integrity-check     <- orphaned references + mixed field types
//   document-bloat-advisor   <- large INCOMPRESSIBLE text (really lands in TOAST)
//   perf-advisor             <- unindexed collections => collection-scan patterns
//   db-config-advisor        <- always reports PG config/cache (no planting needed)
//
// The fixture itself must be REPRODUCIBLE — a determinism scenario cannot be
// seeded with Math.random(). All "random-looking" data below comes from a
// deterministic LCG with a fixed seed, so re-seeding yields identical data.

// ---- deterministic PRNG (fixed seed; NOT Math.random) ---------------------
var _seed = 20260810;
function rnd() {                        // Lehmer / Park-Miller LCG
    _seed = (_seed * 48271) % 2147483647;
    return _seed / 2147483647;
}
function ri(n) { return Math.floor(rnd() * n); }

// Incompressible text pool. PostgreSQL compresses (pglz) before moving a value
// out of line, so a repeated sentence would shrink to nothing and never TOAST.
// A pseudo-random character pool does not compress, so the value really is
// stored out-of-line — which is what document-bloat-advisor looks for.
var CH = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
var POOL = "";
while (POOL.length < 24000) POOL += CH.charAt(ri(CH.length));
function text(n) { return POOL.substr(ri(POOL.length - n - 1), n); }

["accounts", "invoices", "articles", "events"].forEach(function (c) {
    try { db[c].drop(); } catch (e) {}
});


// ---- accounts: redundant indexes ------------------------------------------
var bulk = [];
for (var i = 1; i <= 400; i++) {
    bulk.push({
        account_id: i,
        email: "a" + i + "@example.test",
        tenant_id: (i % 20) + 1,
        status: ["active", "inactive", "pending"][i % 3]
    });
}
db.accounts.insertMany(bulk);
db.accounts.createIndex({ tenant_id: 1 });                       // prefix-redundant
db.accounts.createIndex({ tenant_id: 1, status: 1 });            // keep
db.accounts.createIndex({ email: 1 });                           // duplicate
db.accounts.createIndex({ email: 1 }, { unique: true, name: "email_unique" });

// ---- invoices: orphaned refs + mixed types (data integrity) ---------------
bulk = [];
for (var i = 1; i <= 300; i++) {
    // every 10th invoice points at an account that does not exist
    var acct = (i % 10 === 0) ? 99000 + i : (i % 400) + 1;
    bulk.push({
        invoice_id: i,
        account_id: acct,
        // deliberately mixed type: some amounts are strings
        amount: (i % 7 === 0) ? String(i * 3) : i * 3,
        created_at: new Date(2024, i % 12, (i % 28) + 1)
    });
}
db.invoices.insertMany(bulk);

// ---- articles: large INCOMPRESSIBLE text (document bloat / TOAST) ---------
// ~4 KB of incompressible text per doc, well above PostgreSQL's ~2 KB
// out-of-line threshold, and enough total volume to clear the advisor's
// --min-total-kb floor with a TOAST ratio above its default 0.5.
bulk = [];
for (var i = 1; i <= 250; i++) {
    bulk.push({
        article_id: i,
        title: "Article " + i,
        author_id: (i % 40) + 1,
        body: text(4000),
        notes: text(2000)
    });
}
db.articles.insertMany(bulk);

// ---- events: no secondary indexes -> collection scans ---------------------
bulk = [];
for (var i = 1; i <= 800; i++) {
    bulk.push({
        event_id: i,
        kind: ["click", "view", "purchase"][i % 3],
        user_id: (i % 150) + 1,
        payload_size: (i % 900) + 100
    });
}
db.events.insertMany(bulk);

// ---- traffic so "keep" indexes show real reads ---------------------------
for (var i = 1; i <= 60; i++) {
    db.accounts.find({ tenant_id: (i % 20) + 1, status: "active" }).limit(1).toArray();
    db.accounts.find({ email: "a" + i + "@example.test" }).limit(1).toArray();
    db.events.find({ kind: "purchase" }).limit(1).toArray();
}

print("FIXTURE_READY determinism");
db.getCollectionNames().sort().forEach(function (c) {
    print("  " + c + ": " + db[c].countDocuments() + " docs, " + db[c].getIndexes().length + " indexes");
});
