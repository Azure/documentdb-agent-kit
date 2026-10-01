// Benchmark queries — same on both engines
var results = [];

function time(label, fn) {
    var start = Date.now();
    var count = 0;
    try { count = fn(); } catch(e) { count = -1; }
    var ms = Date.now() - start;
    results.push({label: label, ms: ms, count: count});
    print("  " + ms + "ms\t" + count + "\t" + label);
    return ms;
}

print("═══ POINT QUERIES (find by indexed/unindexed field) ═══");
time("find orders by order_id", function() { return db.orders.find({order_id:"ORD_025000"}).toArray().length; });
time("find orders by customer_id", function() { return db.orders.find({customer_id:"CUST_002500"}).toArray().length; });
time("find orders by status=shipped", function() { return db.orders.find({status:"shipped"}).limit(100).toArray().length; });
time("find orders by status+date sort", function() { return db.orders.find({status:"pending"}).sort({created_at:-1}).limit(20).toArray().length; });
time("find orders by city", function() { return db.orders.find({shipping_city:"Seattle"}).limit(100).toArray().length; });
time("find order_items by order_id", function() { return db.order_items.find({order_id:"ORD_025000"}).toArray().length; });
time("find order_items by product_id", function() { return db.order_items.find({product_id:"PROD_001000"}).toArray().length; });
time("find customers by customer_id", function() { return db.customers.find({customer_id:"CUST_002500"}).toArray().length; });
time("find customers by email", function() { return db.customers.find({email:"cust2500@example.com"}).toArray().length; });
time("find customers by tier+active", function() { return db.customers.find({tier:"gold",is_active:true}).limit(50).toArray().length; });
time("find products by category+price", function() { return db.products.find({category_id:"CAT_005",price:{$gt:100,$lt:300}}).toArray().length; });
time("find products by brand", function() { return db.products.find({brand:"TechPro"}).limit(50).toArray().length; });
time("find reviews by product_id", function() { return db.reviews.find({product_id:"PROD_001000"}).toArray().length; });
time("find reviews by rating>=4", function() { return db.reviews.find({rating:{$gte:4}}).limit(100).toArray().length; });

print("");
print("═══ COUNT QUERIES ═══");
time("count orders", function() { return db.orders.countDocuments(); });
time("count order_items", function() { return db.order_items.countDocuments(); });
time("count reviews", function() { return db.reviews.countDocuments(); });
time("count customers", function() { return db.customers.countDocuments(); });

print("");
print("═══ AGGREGATION QUERIES ═══");
time("agg: revenue by status", function() { return db.orders.aggregate([{$group:{_id:"$status",total:{$sum:"$total_amount"},count:{$sum:1}}}]).toArray().length; });
time("agg: revenue by city (delivered)", function() { return db.orders.aggregate([{$match:{status:"delivered"}},{$group:{_id:"$shipping_city",revenue:{$sum:"$total_amount"}}}]).toArray().length; });
time("agg: top 10 customers by spend", function() { return db.orders.aggregate([{$group:{_id:"$customer_id",total:{$sum:"$total_amount"}}},{$sort:{total:-1}},{$limit:10}]).toArray().length; });
time("agg: top 10 products by qty sold", function() { return db.order_items.aggregate([{$group:{_id:"$product_id",totalQty:{$sum:"$quantity"}}},{$sort:{totalQty:-1}},{$limit:10}]).toArray().length; });
time("agg: avg rating per product (top10)", function() { return db.reviews.aggregate([{$group:{_id:"$product_id",avgRating:{$avg:"$rating"},count:{$sum:1}}},{$sort:{count:-1}},{$limit:10}]).toArray().length; });
time("agg: orders per month", function() { return db.orders.aggregate([{$group:{_id:{$month:"$created_at"},count:{$sum:1},revenue:{$sum:"$total_amount"}}},{$sort:{_id:1}}]).toArray().length; });

print("");
print("═══ LOOKUP / JOIN QUERIES ═══");
time("lookup: order + items (1 order)", function() { return db.orders.aggregate([{$match:{order_id:"ORD_025000"}},{$lookup:{from:"order_items",localField:"order_id",foreignField:"order_id",as:"items"}}]).toArray().length; });
time("lookup: customer orders (1 cust)", function() { return db.orders.aggregate([{$match:{customer_id:"CUST_002500"}},{$lookup:{from:"order_items",localField:"order_id",foreignField:"order_id",as:"items"}},{$limit:10}]).toArray().length; });

print("");
print("═══ EXPLAIN CHECKS (COLLSCAN vs IXSCAN) ═══");
var explainChecks = [
    ["orders", {order_id:"ORD_025000"}],
    ["orders", {status:"shipped"}],
    ["orders", {shipping_city:"Seattle"}],
    ["order_items", {order_id:"ORD_025000"}],
    ["order_items", {product_id:"PROD_001000"}],
    ["customers", {customer_id:"CUST_002500"}],
    ["customers", {email:"cust2500@example.com"}],
    ["products", {category_id:"CAT_005",price:{$gt:100}}],
    ["reviews", {product_id:"PROD_001000"}],
    ["reviews", {rating:{$gte:4}}]
];
explainChecks.forEach(function(c) {
    var plan = db.runCommand({explain:{find:c[0],filter:c[1],limit:1},verbosity:"executionStats"});
    var wp = (plan.queryPlanner||{}).winningPlan||{};
    var es = plan.executionStats||{};
    var stage = wp.stage || (wp.inputStage||{}).stage || "?";
    print("  " + stage + "\t" + (es.totalDocsExamined||0) + " docs\t" + c[0] + " " + JSON.stringify(c[1]).substring(0,50));
});

print("");
var totalMs = results.reduce(function(s,r){return s+r.ms;},0);
var slow = results.filter(function(r){return r.ms>100;}).length;
var moderate = results.filter(function(r){return r.ms>20&&r.ms<=100;}).length;
print("TOTAL: " + totalMs + "ms across " + results.length + " queries (" + slow + " slow, " + moderate + " moderate)");
