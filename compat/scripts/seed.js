import { withDatabase } from "../src/database.js";

const statuses = ["pending", "confirmed", "shipped", "delivered", "cancelled"];
const tiers = ["bronze", "silver", "gold", "platinum"];
const categories = ["electronics", "home", "sports", "books"];

await withDatabase(async (db) => {
  const collections = [
    "customers",
    "products",
    "orders",
    "order_items",
    "inventory"
  ];

  for (const collection of collections) {
    await db.collection(collection).deleteMany({});
  }

  const customers = Array.from({ length: 12 }, (_, index) => {
    const id = index + 1;
    return {
      customer_id: `CUST_${String(id).padStart(3, "0")}`,
      name: `Customer ${id}`,
      tier: tiers[index % tiers.length],
      address: {
        city: ["Seattle", "Portland", "Austin"][index % 3],
        country: "US"
      }
    };
  });

  const products = Array.from({ length: 16 }, (_, index) => {
    const id = index + 1;
    return {
      product_id: `PROD_${String(id).padStart(3, "0")}`,
      name: `Product ${id}`,
      category: categories[index % categories.length],
      price: 15 + id * 7
    };
  });

  const orders = [];
  const orderItems = [];

  for (let index = 0; index < 48; index += 1) {
    const id = index + 1;
    const orderId = `ORD_${String(id).padStart(3, "0")}`;
    const customerId = `CUST_${String((index % 12) + 1).padStart(3, "0")}`;
    const itemCount = (index % 3) + 1;
    let total = 0;

    for (let itemIndex = 0; itemIndex < itemCount; itemIndex += 1) {
      const productNumber = ((index * 3 + itemIndex) % 16) + 1;
      const quantity = itemIndex + 1;
      const unitPrice = 15 + productNumber * 7;
      total += quantity * unitPrice;
      orderItems.push({
        order_id: orderId,
        product_id: `PROD_${String(productNumber).padStart(3, "0")}`,
        quantity,
        unit_price: unitPrice
      });
    }

    orders.push({
      order_id: orderId,
      customer_id: customerId,
      status: statuses[index % statuses.length],
      total_amount: total,
      created_at: new Date(Date.UTC(2025, index % 12, (index % 27) + 1))
    });
  }

  const inventory = [];
  for (let productIndex = 0; productIndex < products.length; productIndex += 1) {
    for (let warehouseIndex = 0; warehouseIndex < 2; warehouseIndex += 1) {
      inventory.push({
        product_id: products[productIndex].product_id,
        warehouse_id: `WH_${warehouseIndex + 1}`,
        quantity: (productIndex + 1) * 9 + warehouseIndex * 4
      });
    }
  }

  await db.collection("customers").insertMany(customers);
  await db.collection("products").insertMany(products);
  await db.collection("orders").insertMany(orders);
  await db.collection("order_items").insertMany(orderItems);
  await db.collection("inventory").insertMany(inventory);

  await Promise.all([
    db.collection("customers").createIndex({ customer_id: 1 }, { unique: true }),
    db.collection("products").createIndex({ product_id: 1 }, { unique: true }),
    db
      .collection("orders")
      .createIndex({ customer_id: 1, status: 1, created_at: -1 }),
    db.collection("orders").createIndex({ order_id: 1 }, { unique: true }),
    db.collection("order_items").createIndex({ order_id: 1 }),
    db.collection("inventory").createIndex({ product_id: 1 })
  ]);

  console.log(
    JSON.stringify({
      database: db.databaseName,
      counts: {
        customers: customers.length,
        products: products.length,
        orders: orders.length,
        order_items: orderItems.length,
        inventory: inventory.length
      }
    })
  );
});
