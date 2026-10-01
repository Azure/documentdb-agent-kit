export async function runQueries(db) {
  const recentShippedOrders = await db
    .collection("orders")
    .find(
      { customer_id: "CUST_003", status: "shipped" },
      {
        projection: {
          _id: 0,
          order_id: 1,
          customer_id: 1,
          status: 1,
          total_amount: 1,
          created_at: 1
        }
      }
    )
    .sort({ created_at: -1 })
    .toArray();

  // SQL analogue:
  // SELECT c.name, COUNT(*), SUM(o.total_amount)
  // FROM orders o JOIN customers c USING (customer_id)
  // GROUP BY c.name ORDER BY SUM(o.total_amount) DESC LIMIT 5;
  const customerOrderSummary = await db
    .collection("orders")
    .aggregate([
      {
        $group: {
          _id: "$customer_id",
          order_count: { $sum: 1 },
          revenue: { $sum: "$total_amount" }
        }
      },
      {
        $lookup: {
          from: "customers",
          localField: "_id",
          foreignField: "customer_id",
          as: "customer"
        }
      },
      { $unwind: "$customer" },
      {
        $project: {
          _id: 0,
          customer_id: "$_id",
          customer_name: "$customer.name",
          tier: "$customer.tier",
          order_count: 1,
          revenue: 1
        }
      },
      { $sort: { revenue: -1, customer_id: 1 } },
      { $limit: 5 }
    ])
    .toArray();

  // SQL analogue:
  // SELECT o.*, c.name, oi.*
  // FROM orders o
  // JOIN customers c USING (customer_id)
  // JOIN order_items oi USING (order_id)
  // WHERE o.order_id = 'ORD_018';
  const orderDetails = await db
    .collection("orders")
    .aggregate([
      { $match: { order_id: "ORD_018" } },
      {
        $lookup: {
          from: "customers",
          localField: "customer_id",
          foreignField: "customer_id",
          as: "customer"
        }
      },
      { $unwind: "$customer" },
      {
        $lookup: {
          from: "order_items",
          localField: "order_id",
          foreignField: "order_id",
          as: "items"
        }
      },
      {
        $project: {
          _id: 0,
          order_id: 1,
          customer_id: 1,
          customer_name: "$customer.name",
          status: 1,
          total_amount: 1,
          item_count: { $size: "$items" },
          items: {
            product_id: 1,
            quantity: 1,
            unit_price: 1
          }
        }
      }
    ])
    .toArray();

  // SQL analogue:
  // SELECT p.product_id, p.name, SUM(i.quantity)
  // FROM products p JOIN inventory i USING (product_id)
  // GROUP BY p.product_id, p.name ORDER BY SUM(i.quantity), p.product_id;
  const productInventory = await db
    .collection("products")
    .aggregate([
      {
        $lookup: {
          from: "inventory",
          localField: "product_id",
          foreignField: "product_id",
          as: "stock"
        }
      },
      {
        $project: {
          _id: 0,
          product_id: 1,
          product_name: "$name",
          category: 1,
          warehouse_count: { $size: "$stock" },
          total_quantity: { $sum: "$stock.quantity" }
        }
      },
      { $sort: { total_quantity: 1, product_id: 1 } },
      { $limit: 5 }
    ])
    .toArray();

  // $lookup does not guarantee array ordering. Normalize client-side so exact
  // result verification does not mistake an allowed order difference for a
  // query failure.
  for (const order of orderDetails) {
    order.items.sort((left, right) =>
      left.product_id.localeCompare(right.product_id)
    );
  }

  return {
    recentShippedOrders,
    customerOrderSummary,
    orderDetails,
    productInventory
  };
}
