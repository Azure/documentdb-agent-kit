// Seed identical ecommerce data — deterministic so both DBs get same docs
var rng_seed = 42;
function rng() { rng_seed = (rng_seed * 1103515245 + 12345) & 0x7fffffff; return rng_seed / 0x7fffffff; }
function rngInt(min,max) { return min + Math.floor(rng() * (max-min+1)); }
function pad(n,w) { var s=String(n); while(s.length<w) s="0"+s; return s; }

// Categories
var cats = []; for (var i=1;i<=10;i++) cats.push({category_id:"CAT_"+pad(i,3),name:"Category "+i});
db.categories.insertMany(cats);

// Suppliers
var sups = []; for (var i=1;i<=50;i++) sups.push({supplier_id:"SUP_"+pad(i,3),name:"Supplier "+i,contact:"sup"+i+"@example.com"});
db.suppliers.insertMany(sups);

// Customers
var tiers=["bronze","silver","gold","platinum"];
var cities=["Seattle","Portland","Denver","Austin","Chicago","Boston","Miami","Phoenix","Dallas","Atlanta"];
for (var batch=0;batch<10;batch++) {
    var custs=[];
    for (var i=batch*500;i<(batch+1)*500;i++) {
        custs.push({customer_id:"CUST_"+pad(i,6),name:"Customer "+i,email:"cust"+i+"@example.com",
            tier:tiers[rngInt(0,3)],is_active:rng()>0.1,loyalty_points:rngInt(0,10000),
            address:{city:cities[rngInt(0,9)],state:"ST",zip:pad(rngInt(10000,99999),5)},
            username:"user"+pad(i,6),created_at:new Date(2024,rngInt(0,11),rngInt(1,28))});
    }
    db.customers.insertMany(custs);
}
print("  Customers: "+db.customers.countDocuments());

// Products
var brands=["TechPro","GadgetX","SmartHome","EcoLife","FitGear","StyleCo","NatureWell","PowerMax","CoolTech","SafeGuard"];
var prods=[];
for (var i=0;i<2000;i++) {
    prods.push({product_id:"PROD_"+pad(i,6),name:"Product "+i,category_id:"CAT_"+pad(rngInt(1,10),3),
        supplier_id:"SUP_"+pad(rngInt(1,50),3),brand:brands[rngInt(0,9)],price:Math.round(rng()*500*100)/100,
        cost:Math.round(rng()*200*100)/100,active:rng()>0.05,tags:["tag"+rngInt(1,20),"tag"+rngInt(1,20)]});
}
db.products.insertMany(prods);
print("  Products: "+db.products.countDocuments());

// Inventory
var whs=["WH_EAST","WH_WEST","WH_CENTRAL"];
var invs=[];
for (var i=0;i<2000;i++) {
    var nw=rngInt(1,3);
    for (var w=0;w<nw;w++) {
        invs.push({product_id:"PROD_"+pad(i,6),warehouse_id:whs[rngInt(0,2)],quantity:rngInt(0,500),reserved:rngInt(0,50)});
    }
}
db.inventory.insertMany(invs);
print("  Inventory: "+db.inventory.countDocuments());

// Orders + Order Items
var statuses=["pending","confirmed","shipped","delivered","cancelled"];
var payments=["credit_card","paypal","bank_transfer","crypto"];
for (var batch=0;batch<50;batch++) {
    var ords=[], items=[];
    for (var i=batch*1000;i<(batch+1)*1000;i++) {
        var nItems=rngInt(1,5);
        var total=0;
        for (var j=0;j<nItems;j++) {
            var price=Math.round(rng()*200*100)/100;
            var qty=rngInt(1,5);
            total+=price*qty;
            items.push({order_id:"ORD_"+pad(i,6),product_id:"PROD_"+pad(rngInt(0,1999),6),
                quantity:qty,unit_price:price,discount:rng()>0.7?Math.round(rng()*20*100)/100:0});
        }
        ords.push({order_id:"ORD_"+pad(i,6),customer_id:"CUST_"+pad(rngInt(0,4999),6),
            status:statuses[rngInt(0,4)],payment_method:payments[rngInt(0,3)],
            total_amount:Math.round(total*100)/100,
            shipping_city:cities[rngInt(0,9)],
            created_at:new Date(2024,rngInt(0,11),rngInt(1,28))});
    }
    db.orders.insertMany(ords);
    db.order_items.insertMany(items);
}
print("  Orders: "+db.orders.countDocuments()+", Order Items: "+db.order_items.countDocuments());

// Reviews
for (var batch=0;batch<25;batch++) {
    var revs=[];
    for (var i=batch*1000;i<(batch+1)*1000;i++) {
        revs.push({review_id:"REV_"+pad(i,6),product_id:"PROD_"+pad(rngInt(0,1999),6),
            customer_id:"CUST_"+pad(rngInt(0,4999),6),order_id:"ORD_"+pad(rngInt(0,49999),6),
            rating:rngInt(1,5),title:"Review "+i,text:"This is review text for item "+i,
            helpful_votes:rngInt(0,50),created_at:new Date(2024,rngInt(0,11),rngInt(1,28))});
    }
    db.reviews.insertMany(revs);
}
print("  Reviews: "+db.reviews.countDocuments());

print("SEED COMPLETE");
