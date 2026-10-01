import assert from "node:assert/strict";
import { withDatabase } from "../src/database.js";
import { runQueries } from "../src/queries.js";

const result = await withDatabase(runQueries);

assert.deepEqual(
  result.recentShippedOrders.map((order) => order.order_id),
  ["ORD_003"],
  "recent shipped orders changed"
);

assert.deepEqual(
  result.customerOrderSummary.map(
    ({ customer_id, customer_name, tier, order_count, revenue }) => ({
      customer_id,
      customer_name,
      tier,
      order_count,
      revenue
    })
  ),
  [
    {
      customer_id: "CUST_012",
      customer_name: "Customer 12",
      tier: "platinum",
      order_count: 4,
      revenue: 1928
    },
    {
      customer_id: "CUST_003",
      customer_name: "Customer 3",
      tier: "gold",
      order_count: 4,
      revenue: 1760
    },
    {
      customer_id: "CUST_009",
      customer_name: "Customer 9",
      tier: "bronze",
      order_count: 4,
      revenue: 1760
    },
    {
      customer_id: "CUST_006",
      customer_name: "Customer 6",
      tier: "silver",
      order_count: 4,
      revenue: 1704
    },
    {
      customer_id: "CUST_011",
      customer_name: "Customer 11",
      tier: "gold",
      order_count: 4,
      revenue: 992
    }
  ],
  "customer revenue join changed"
);

assert.equal(result.orderDetails.length, 1);
assert.deepEqual(
  {
    order_id: result.orderDetails[0].order_id,
    customer_id: result.orderDetails[0].customer_id,
    customer_name: result.orderDetails[0].customer_name,
    status: result.orderDetails[0].status,
    total_amount: result.orderDetails[0].total_amount,
    item_count: result.orderDetails[0].item_count
  },
  {
    order_id: "ORD_018",
    customer_id: "CUST_006",
    customer_name: "Customer 6",
    status: "shipped",
    total_amount: 314,
    item_count: 3
  },
  "order/customer/items join changed"
);

assert.deepEqual(
  result.productInventory.map(
    ({ product_id, product_name, category, warehouse_count, total_quantity }) => ({
      product_id,
      product_name,
      category,
      warehouse_count,
      total_quantity
    })
  ),
  [
    {
      product_id: "PROD_001",
      product_name: "Product 1",
      category: "electronics",
      warehouse_count: 2,
      total_quantity: 22
    },
    {
      product_id: "PROD_002",
      product_name: "Product 2",
      category: "home",
      warehouse_count: 2,
      total_quantity: 40
    },
    {
      product_id: "PROD_003",
      product_name: "Product 3",
      category: "sports",
      warehouse_count: 2,
      total_quantity: 58
    },
    {
      product_id: "PROD_004",
      product_name: "Product 4",
      category: "books",
      warehouse_count: 2,
      total_quantity: 76
    },
    {
      product_id: "PROD_005",
      product_name: "Product 5",
      category: "electronics",
      warehouse_count: 2,
      total_quantity: 94
    }
  ],
  "product/inventory join changed"
);

console.log(
  JSON.stringify({
    status: "PASS",
    checks: 4,
    query_shapes: {
      find: 1,
      lookup_aggregations: 3
    }
  })
);
