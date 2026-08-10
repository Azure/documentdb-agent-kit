#!/usr/bin/env bash
# seed.sh — Generate the large "ecommerce" demo dataset for perf/diagnostic testing
# Creates: customers (5K), products (2K), orders (50K), order_items (150K),
#          reviews (25K), inventory (4K)
# Usage: export DB_PASSWORD='<your-password>'; bash scenarios/ecommerce/seed.sh [--container NAME] [--password PASS]
set -uo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-documentdb-local}"
PORT="${PORT:-10260}"
USER="${DB_USER:-docdbadmin}"
PASSWORD="${DB_PASSWORD:-}"
DB="ecommerce"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --container)  CONTAINER_NAME="$2"; shift 2;;
        --password)   PASSWORD="$2"; shift 2;;
        --port)       PORT="$2"; shift 2;;
        --db)         DB="$2"; shift 2;;
        -h|--help)    echo "Usage: $0 [--container NAME] [--password PASS] [--port PORT] [--db NAME]"; exit 0;;
        *)            shift;;
    esac
done

[[ -z "$PASSWORD" ]] && { echo "Error: no password. Set DB_PASSWORD or pass --password (e.g. export DB_PASSWORD='<your-password>')." >&2; exit 1; }

run_mongosh() {
    docker exec -u documentdb "$CONTAINER_NAME" mongosh \
        "localhost:${PORT}/${DB}" -u "$USER" -p "$PASSWORD" \
        --authenticationMechanism SCRAM-SHA-256 --tls --tlsAllowInvalidCertificates \
        --quiet --eval "$1" 2>/dev/null
}

echo "═══════════════════════════════════════════════════════════════"
echo "  Seeding ecommerce data into ${DB} (container: ${CONTAINER_NAME})"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ── Categories & Suppliers (static) ──────────────────────────────────
echo "→ Creating categories and suppliers..."
run_mongosh '
db.categories.drop();
db.suppliers.drop();
db.categories.insertMany([
    {category_id:"CAT_001", name:"Electronics", parent:null},
    {category_id:"CAT_002", name:"Clothing", parent:null},
    {category_id:"CAT_003", name:"Home & Garden", parent:null},
    {category_id:"CAT_004", name:"Sports", parent:null},
    {category_id:"CAT_005", name:"Books", parent:null},
    {category_id:"CAT_006", name:"Phones", parent:"CAT_001"},
    {category_id:"CAT_007", name:"Computers", parent:"CAT_001"},
    {category_id:"CAT_008", name:"Men", parent:"CAT_002"},
    {category_id:"CAT_009", name:"Women", parent:"CAT_002"},
    {category_id:"CAT_010", name:"Outdoor", parent:"CAT_004"}
]);
var suppliers = [];
for (var i = 0; i < 50; i++) {
    suppliers.push({
        supplier_id: "SUP_" + String(i).padStart(3,"0"),
        name: "Supplier " + i,
        contact_email: "contact@supplier" + i + ".com",
        rating: Math.round((3 + Math.random()*2)*10)/10,
        active: Math.random() > 0.1
    });
}
db.suppliers.insertMany(suppliers);
print("  Categories: " + db.categories.countDocuments() + ", Suppliers: " + db.suppliers.countDocuments());
'

# ── Customers (5000) ─────────────────────────────────────────────────
echo "→ Creating 5000 customers..."
run_mongosh '
db.customers.drop();
var cities = ["New York","Los Angeles","Chicago","Houston","Phoenix","Philadelphia","San Antonio","San Diego","Dallas","San Jose","Austin","Seattle","Denver","Boston","Portland"];
var tiers = ["bronze","silver","gold","platinum"];
var batch = [];
for (var i = 0; i < 5000; i++) {
    batch.push({
        customer_id: "CUST_" + String(i).padStart(6,"0"),
        name: "Customer " + i,
        email: "user" + i + "@example.com",
        tier: tiers[Math.floor(Math.random()*4)],
        loyalty_points: Math.floor(Math.random()*10000),
        address: {
            city: cities[Math.floor(Math.random()*15)],
            state: "US",
            zipCode: String(10000 + Math.floor(Math.random()*90000))
        },
        is_active: Math.random() > 0.05,
        created_at: new Date(2023, Math.floor(Math.random()*24), Math.floor(Math.random()*28)+1),
        last_login: new Date(2024, Math.floor(Math.random()*12), Math.floor(Math.random()*28)+1)
    });
    if (batch.length >= 1000) { db.customers.insertMany(batch); batch = []; }
}
if (batch.length > 0) db.customers.insertMany(batch);
print("  Customers: " + db.customers.countDocuments());
'

# ── Products (2000) ──────────────────────────────────────────────────
echo "→ Creating 2000 products..."
run_mongosh '
db.products.drop();
var cats = ["CAT_001","CAT_002","CAT_003","CAT_004","CAT_005","CAT_006","CAT_007","CAT_008","CAT_009","CAT_010"];
var brands = ["TechPro","StyleMax","HomeFirst","SportElite","BookWorld","PhoneZone","CompuMax","FashionFwd","OutdoorGear","GadgetCo"];
var batch = [];
for (var i = 0; i < 2000; i++) {
    var price = Math.round((10 + Math.random()*990)*100)/100;
    batch.push({
        product_id: "PROD_" + String(i).padStart(6,"0"),
        name: "Product " + i,
        description: "Description for product " + i + " with detailed specifications",
        category_id: cats[Math.floor(Math.random()*10)],
        brand: brands[Math.floor(Math.random()*10)],
        supplier_id: "SUP_" + String(Math.floor(Math.random()*50)).padStart(3,"0"),
        price: price,
        cost: Math.round(price * (0.3 + Math.random()*0.4) * 100)/100,
        currency: "USD",
        active: Math.random() > 0.05,
        ratings: { average: Math.round(Math.random()*5*10)/10, count: Math.floor(Math.random()*500) },
        tags: [cats[Math.floor(Math.random()*10)].toLowerCase(), Math.random()>0.5?"sale":"regular", Math.random()>0.7?"featured":"standard"],
        created_at: new Date(2023, Math.floor(Math.random()*12), Math.floor(Math.random()*28)+1),
        updated_at: new Date()
    });
    if (batch.length >= 500) { db.products.insertMany(batch); batch = []; }
}
if (batch.length > 0) db.products.insertMany(batch);
print("  Products: " + db.products.countDocuments());
'

# ── Inventory (4000) ─────────────────────────────────────────────────
echo "→ Creating inventory records..."
run_mongosh '
db.inventory.drop();
var warehouses = ["WH_EAST","WH_WEST","WH_CENTRAL","WH_SOUTH"];
var batch = [];
for (var i = 0; i < 2000; i++) {
    var pid = "PROD_" + String(i).padStart(6,"0");
    var numWH = 1 + Math.floor(Math.random()*3);
    var whs = warehouses.slice().sort(function(){return Math.random()-0.5}).slice(0, numWH);
    whs.forEach(function(wh) {
        var qty = Math.floor(Math.random()*200);
        batch.push({
            product_id: pid,
            warehouse_id: wh,
            quantity: qty,
            reserved: Math.min(Math.floor(Math.random()*50), qty),
            reorder_point: 10 + Math.floor(Math.random()*40),
            last_restocked: new Date(2024, Math.floor(Math.random()*12), Math.floor(Math.random()*28)+1)
        });
    });
    if (batch.length >= 1000) { db.inventory.insertMany(batch); batch = []; }
}
if (batch.length > 0) db.inventory.insertMany(batch);
print("  Inventory: " + db.inventory.countDocuments());
'

# ── Orders (50K) + Order Items (150K) ────────────────────────────────
echo "→ Creating 50000 orders + order items (this takes a minute)..."
run_mongosh '
db.orders.drop();
db.order_items.drop();
var statuses = ["pending","confirmed","shipped","delivered","cancelled"];
var methods = ["credit_card","debit_card","paypal","bank_transfer","crypto"];
var orderBatch = [];
var itemBatch = [];
for (var i = 0; i < 50000; i++) {
    var oid = "ORD_" + String(i).padStart(6,"0");
    var cid = "CUST_" + String(Math.floor(Math.random()*5000)).padStart(6,"0");
    var st = statuses[Math.floor(Math.random()*5)];
    var d = new Date(2024, Math.floor(Math.random()*12), Math.floor(Math.random()*28)+1);
    var numItems = 1 + Math.floor(Math.random()*5);
    var total = 0;
    orderBatch.push({
        order_id: oid,
        customer_id: cid,
        status: st,
        payment_method: methods[Math.floor(Math.random()*5)],
        created_at: d,
        updated_at: new Date(d.getTime() + Math.random()*86400000*3),
        shipping_city: ["New York","LA","Chicago","Houston","Phoenix","Seattle","Denver","Boston","Portland","Austin"][Math.floor(Math.random()*10)]
    });
    for (var j = 0; j < numItems; j++) {
        var pid = "PROD_" + String(Math.floor(Math.random()*2000)).padStart(6,"0");
        var qty = 1 + Math.floor(Math.random()*5);
        var price = Math.round((10 + Math.random()*490)*100)/100;
        var disc = [0,0,0,0.1,0.15,0.2][Math.floor(Math.random()*6)];
        total += qty * price * (1-disc);
        itemBatch.push({
            order_id: oid,
            product_id: pid,
            quantity: qty,
            unit_price: price,
            discount: disc
        });
    }
    // Update order total
    orderBatch[orderBatch.length-1].total_amount = Math.round(total*100)/100;

    if (orderBatch.length >= 2000) {
        db.orders.insertMany(orderBatch);
        db.order_items.insertMany(itemBatch);
        orderBatch = []; itemBatch = [];
    }
}
if (orderBatch.length > 0) { db.orders.insertMany(orderBatch); db.order_items.insertMany(itemBatch); }
print("  Orders: " + db.orders.countDocuments() + ", Order Items: " + db.order_items.countDocuments());
'

# ── Reviews (25K) ────────────────────────────────────────────────────
echo "→ Creating 25000 reviews..."
run_mongosh '
db.reviews.drop();
var batch = [];
for (var i = 0; i < 25000; i++) {
    var rating = [1,2,3,3,4,4,4,5,5,5][Math.floor(Math.random()*10)];
    batch.push({
        review_id: "REV_" + String(i).padStart(6,"0"),
        product_id: "PROD_" + String(Math.floor(Math.random()*2000)).padStart(6,"0"),
        customer_id: "CUST_" + String(Math.floor(Math.random()*5000)).padStart(6,"0"),
        order_id: "ORD_" + String(Math.floor(Math.random()*50000)).padStart(6,"0"),
        rating: rating,
        title: rating >= 4 ? "Great product" : rating >= 3 ? "Decent product" : "Disappointing",
        text: "Review text for item " + i,
        verified_purchase: Math.random() > 0.1,
        created_at: new Date(2024, Math.floor(Math.random()*12), Math.floor(Math.random()*28)+1),
        helpful_votes: Math.floor(Math.random()*50)
    });
    if (batch.length >= 2000) { db.reviews.insertMany(batch); batch = []; }
}
if (batch.length > 0) db.reviews.insertMany(batch);
print("  Reviews: " + db.reviews.countDocuments());
'

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Data seeding complete!"
echo "═══════════════════════════════════════════════════════════════"
run_mongosh '
var colls = db.getCollectionNames().sort();
var total = 0;
colls.forEach(function(c) {
    var cnt = db[c].countDocuments();
    total += cnt;
    print("  " + c + ": " + cnt + " docs");
});
print("  ──────────────────");
print("  TOTAL: " + total + " documents");
'
