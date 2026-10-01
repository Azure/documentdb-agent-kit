import { createHash } from "node:crypto";
import {
  mkdir,
  readdir,
  rm,
  writeFile
} from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const scenarioRoot = resolve(here, "..");

const outputArgument = process.argv.indexOf("--output");
const outputRoot =
  outputArgument >= 0
    ? resolve(process.argv[outputArgument + 1])
    : join(scenarioRoot, "data");

const DATASET_VERSION = "1.0.0";
const SEED = 20260901;
const GENERATED_AT = "2026-09-01T00:00:00.000Z";
const DATA_EPOCH = "2025-01-01T00:00:00.000Z";
const DAY_MS = 86_400_000;

const collectionsRoot = join(outputRoot, "collections");
const casesRoot = join(outputRoot, "cases");

function dateValue(day, hour = 0) {
  return {
    $date: new Date(
      Date.parse(DATA_EPOCH) + day * DAY_MS + hour * 3_600_000
    ).toISOString()
  };
}

function round2(value) {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function padded(prefix, value, width = 4) {
  return `${prefix}_${String(value).padStart(width, "0")}`;
}

function stableJson(value) {
  return `${JSON.stringify(value, null, 2)}\n`;
}

function jsonLine(value) {
  return `${JSON.stringify(value)}\n`;
}

function sha256(content) {
  return createHash("sha256").update(content).digest("hex");
}

async function writeJsonl(relativePath, rows) {
  const content = rows.map(jsonLine).join("");
  const path = join(outputRoot, relativePath);
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, content);
  return {
    path: relativePath,
    records: rows.length,
    bytes: Buffer.byteLength(content),
    sha256: sha256(content)
  };
}

async function writeJson(relativePath, value) {
  const content = stableJson(value);
  const path = join(outputRoot, relativePath);
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, content);
  return {
    path: relativePath,
    records: Array.isArray(value) ? value.length : 1,
    bytes: Buffer.byteLength(content),
    sha256: sha256(content)
  };
}

await rm(outputRoot, { recursive: true, force: true });
await mkdir(collectionsRoot, { recursive: true });
await mkdir(casesRoot, { recursive: true });

const regions = ["amer", "emea", "apac", "canada"];
const cities = ["Seattle", "Portland", "Austin", "Toronto", "London", "Tokyo"];
const tiers = ["bronze", "silver", "gold", "platinum"];
const categories = ["electronics", "home", "sports", "books", "outdoor"];
const brands = ["Northwind", "Contoso", "Fabrikam", "Adventure", "Litware"];
const statuses = ["pending", "confirmed", "shipped", "delivered", "cancelled"];
const channels = ["web", "mobile", "marketplace"];
const paymentMethods = ["card", "bank_transfer", "wallet"];
const warehouses = ["WH_EAST", "WH_WEST", "WH_CENTRAL"];

const customers = Array.from({ length: 200 }, (_, index) => {
  const number = index + 1;
  return {
    customer_id: padded("CUST", number),
    name: `Customer ${number}`,
    email: `customer${number}@example.test`,
    tier: tiers[index % tiers.length],
    region: regions[index % regions.length],
    address: {
      city: cities[index % cities.length],
      country: index % 7 === 0 ? "CA" : "US",
      postal_code: String(10000 + ((index * 7919) % 89999))
    },
    segments: [
      index % 3 === 0 ? "frequent" : "standard",
      index % 5 === 0 ? "promotion" : "full-price"
    ],
    created_at: dateValue(-(365 + (index % 730)))
  };
});

const products = Array.from({ length: 100 }, (_, index) => {
  const number = index + 1;
  const price = round2(12 + number * 3.75);
  return {
    product_id: padded("PROD", number),
    name: `Product ${number}`,
    category: categories[index % categories.length],
    brand: brands[index % brands.length],
    price,
    cost: round2(price * (0.42 + (index % 4) * 0.06)),
    active: index % 17 !== 0,
    tags: [
      categories[index % categories.length],
      index % 2 === 0 ? "featured" : "standard",
      index % 7 === 0 ? "seasonal" : "evergreen"
    ],
    attributes: {
      color: ["black", "blue", "green", "red"][index % 4],
      size: ["small", "medium", "large"][index % 3],
      weight_kg: round2(0.25 + (index % 12) * 0.18)
    },
    ratings: {
      average: round2(3.2 + (index % 18) / 10),
      count: 15 + ((index * 37) % 480)
    },
    created_at: dateValue(-(180 + (index % 365)))
  };
});

const inventory = [];
for (let productIndex = 0; productIndex < products.length; productIndex += 1) {
  for (let warehouseIndex = 0; warehouseIndex < warehouses.length; warehouseIndex += 1) {
    const productNumber = productIndex + 1;
    let quantity = 20 + ((productNumber * 17 + warehouseIndex * 23) % 180);

    // Transaction edge cases all target WH_EAST.
    if (warehouseIndex === 0 && productNumber === 1) quantity = 10;
    if (warehouseIndex === 0 && productNumber === 2) quantity = 1;
    if (warehouseIndex === 0 && productNumber === 3) quantity = 0;
    if (warehouseIndex === 0 && productNumber === 4) quantity = 25;

    inventory.push({
      inventory_id: `${padded("PROD", productNumber)}:${warehouses[warehouseIndex]}`,
      product_id: padded("PROD", productNumber),
      warehouse_id: warehouses[warehouseIndex],
      quantity,
      reserved: quantity === 0 ? 0 : Math.min(quantity, (productNumber + warehouseIndex) % 6),
      reorder_point: 12 + (productNumber % 18),
      version: 1,
      updated_at: dateValue(89, warehouseIndex)
    });
  }
}

const orders = [];
const orderItems = [];
const payments = [];

for (let orderIndex = 0; orderIndex < 2000; orderIndex += 1) {
  const orderNumber = orderIndex + 1;
  const orderId = padded("ORD", orderNumber, 6);
  const customerNumber = ((orderIndex * 17) % customers.length) + 1;
  const itemCount = (orderIndex % 5) + 1;
  let total = 0;

  for (let itemIndex = 0; itemIndex < itemCount; itemIndex += 1) {
    const productNumber =
      ((orderIndex * 11 + itemIndex * 7) % products.length) + 1;
    const product = products[productNumber - 1];
    const quantity = (itemIndex % 3) + 1;
    const discountRate = [0, 0, 0.05, 0.1, 0.15][
      (orderIndex + itemIndex) % 5
    ];
    const lineTotal = round2(product.price * quantity * (1 - discountRate));
    total = round2(total + lineTotal);

    orderItems.push({
      order_item_id: `${orderId}:${itemIndex + 1}`,
      order_id: orderId,
      line_number: itemIndex + 1,
      product_id: product.product_id,
      quantity,
      unit_price: product.price,
      discount_rate: discountRate,
      line_total: lineTotal
    });
  }

  const status = statuses[orderIndex % statuses.length];
  const placedDay = orderIndex % 90;
  orders.push({
    order_id: orderId,
    customer_id: padded("CUST", customerNumber),
    status,
    region: regions[orderIndex % regions.length],
    channel: channels[orderIndex % channels.length],
    currency: "USD",
    item_count: itemCount,
    total_amount: total,
    placed_at: dateValue(placedDay, orderIndex % 20),
    updated_at: dateValue(placedDay, (orderIndex % 20) + 1),
    shipping: {
      city: cities[orderIndex % cities.length],
      method: ["standard", "express", "pickup"][orderIndex % 3]
    }
  });

  payments.push({
    payment_id: padded("PAY", orderNumber, 6),
    order_id: orderId,
    customer_id: padded("CUST", customerNumber),
    amount: total,
    currency: "USD",
    method: paymentMethods[orderIndex % paymentMethods.length],
    status: status === "cancelled" ? "reversed" : "captured",
    processed_at: dateValue(placedDay, (orderIndex % 20) + 2)
  });
}

const deliveredOrders = orders.filter((order) => order.status === "delivered");
const returns = deliveredOrders.slice(0, 120).map((order, index) => {
  const firstItem = orderItems.find(
    (item) => item.order_id === order.order_id && item.line_number === 1
  );
  return {
    return_id: padded("RET", index + 1, 5),
    order_id: order.order_id,
    customer_id: order.customer_id,
    product_id: firstItem.product_id,
    amount: firstItem.line_total,
    reason: ["damaged", "wrong_item", "changed_mind"][index % 3],
    status: ["requested", "approved", "refunded"][index % 3],
    created_at: dateValue(60 + (index % 30), 12)
  };
});

const missingSalesDays = new Set([7, 19, 36, 57, 78, 85]);
const nullRevenueDays = new Set([14, 43, 69]);
const dailySales = [];

for (let day = 0; day < 90; day += 1) {
  if (missingSalesDays.has(day)) continue;
  // Revenue is formula-derived rather than queried, keeping generation
  // independent of a database engine.
  const revenue = round2(
    orders
      .filter((_, orderIndex) => orderIndex % 90 === day)
      .reduce((sum, order) => sum + order.total_amount, 0)
  );
  dailySales.push({
    sales_date: dateValue(day),
    revenue: nullRevenueDays.has(day) ? null : revenue,
    order_count: orders.filter((_, orderIndex) => orderIndex % 90 === day).length,
    units: orderItems
      .filter((item) => {
        const orderNumber = Number(item.order_id.slice(4));
        return (orderNumber - 1) % 90 === day;
      })
      .reduce((sum, item) => sum + item.quantity, 0),
    promotion_active: day % 14 < 4,
    note: nullRevenueDays.has(day) ? "intentional null for $fill" : null
  });
}

const streamOrders = [
  {
    order_id: "STREAM_BASE_001",
    customer_id: "CUST_0001",
    status: "pending",
    total_amount: 25,
    version: 1,
    updated_at: dateValue(89, 20)
  },
  {
    order_id: "STREAM_BASE_002",
    customer_id: "CUST_0002",
    status: "confirmed",
    total_amount: 40,
    version: 1,
    updated_at: dateValue(89, 21)
  }
];

const transactionCases = [
  {
    case_id: "commit-purchase",
    description: "Insert order, item, and payment; decrement stock atomically.",
    product_id: "PROD_0001",
    warehouse_id: "WH_EAST",
    quantity: 2,
    initial_quantity: 10,
    expected_quantity: 8,
    order_id: "TXN_ORDER_COMMIT",
    payment_id: "TXN_PAYMENT_COMMIT",
    expected: "commit"
  },
  {
    case_id: "forced-rollback",
    description: "Throw after payment insert; all writes and stock update roll back.",
    product_id: "PROD_0004",
    warehouse_id: "WH_EAST",
    quantity: 3,
    initial_quantity: 25,
    expected_quantity: 25,
    order_id: "TXN_ORDER_ROLLBACK",
    payment_id: "TXN_PAYMENT_ROLLBACK",
    failure_after: "payment_insert",
    expected: "rollback"
  },
  {
    case_id: "insufficient-stock",
    description: "Reject purchase and leave no order/payment when inventory is zero.",
    product_id: "PROD_0003",
    warehouse_id: "WH_EAST",
    quantity: 1,
    initial_quantity: 0,
    expected_quantity: 0,
    order_id: "TXN_ORDER_NO_STOCK",
    payment_id: "TXN_PAYMENT_NO_STOCK",
    expected: "rollback"
  },
  {
    case_id: "concurrent-last-unit",
    description: "Two concurrent purchases target the last unit; exactly one commits.",
    product_id: "PROD_0002",
    warehouse_id: "WH_EAST",
    quantity: 1,
    initial_quantity: 1,
    expected_quantity: 0,
    competing_order_ids: ["TXN_ORDER_RACE_A", "TXN_ORDER_RACE_B"],
    expected_commits: 1
  }
];

const changeStreamCases = [
  {
    sequence: 1,
    operation: "insert",
    collection: "stream_orders",
    document: {
      order_id: "STREAM_NEW_001",
      customer_id: "CUST_0003",
      status: "pending",
      total_amount: 55,
      version: 1,
      updated_at: dateValue(89, 22)
    },
    expected_operation_type: "insert"
  },
  {
    sequence: 2,
    operation: "update",
    collection: "stream_orders",
    filter: { order_id: "STREAM_BASE_001" },
    update: {
      $set: {
        status: "shipped",
        version: 2,
        updated_at: dateValue(89, 23)
      }
    },
    expected_operation_type: "update"
  },
  {
    sequence: 3,
    operation: "replace",
    collection: "stream_orders",
    filter: { order_id: "STREAM_BASE_002" },
    replacement: {
      order_id: "STREAM_BASE_002",
      customer_id: "CUST_0002",
      status: "delivered",
      total_amount: 40,
      version: 2,
      updated_at: dateValue(89, 23)
    },
    expected_operation_type: "replace"
  },
  {
    sequence: 4,
    operation: "delete",
    collection: "stream_orders",
    filter: { order_id: "STREAM_NEW_001" },
    expected_operation_type: "delete"
  }
];

const aggregationCases = [
  {
    case_id: "facet-order-dashboard",
    purpose: "$facet with status counts, revenue totals, and top customers.",
    collections: ["orders"],
    stages: ["$match", "$facet", "$group", "$sort", "$limit"]
  },
  {
    case_id: "pipeline-lookup-order-items",
    purpose: "Correlated $lookup using let and $expr.",
    collections: ["orders", "order_items"],
    stages: ["$match", "$lookup", "$expr", "$project"]
  },
  {
    case_id: "window-customer-running-total",
    purpose: "$setWindowFields partitioned by customer and sorted by date.",
    collections: ["orders"],
    stages: ["$setWindowFields", "$sum", "$documentNumber"]
  },
  {
    case_id: "daily-sales-densify-fill",
    purpose: "$densify missing days and $fill intentional null revenue values.",
    collections: ["daily_sales"],
    stages: ["$densify", "$fill", "$dateTrunc"]
  },
  {
    case_id: "order-return-union",
    purpose: "$unionWith orders and returns into one activity stream.",
    collections: ["orders", "returns"],
    stages: ["$unionWith", "$project", "$sort", "$limit"]
  },
  {
    case_id: "product-price-buckets",
    purpose: "$bucket price bands and aggregate product tag arrays.",
    collections: ["products"],
    stages: ["$bucket", "$map", "$filter", "$reduce", "$sortArray"]
  },
  {
    case_id: "materialize-customer-summary",
    purpose: "$merge a repeatable customer summary into a target collection.",
    collections: ["orders", "customer_summaries"],
    stages: ["$group", "$set", "$merge"]
  }
];

const indexes = {
  customers: [
    { name: "customer_id_1", key: { customer_id: 1 }, unique: true },
    { name: "region_1_tier_1", key: { region: 1, tier: 1 } }
  ],
  products: [
    { name: "product_id_1", key: { product_id: 1 }, unique: true },
    { name: "category_1_price_1", key: { category: 1, price: 1 } },
    { name: "tags_1", key: { tags: 1 } }
  ],
  inventory: [
    {
      name: "product_id_1_warehouse_id_1",
      key: { product_id: 1, warehouse_id: 1 },
      unique: true
    }
  ],
  orders: [
    { name: "order_id_1", key: { order_id: 1 }, unique: true },
    {
      name: "customer_id_1_placed_at_-1",
      key: { customer_id: 1, placed_at: -1 }
    },
    { name: "status_1_placed_at_-1", key: { status: 1, placed_at: -1 } }
  ],
  order_items: [
    {
      name: "order_id_1_line_number_1",
      key: { order_id: 1, line_number: 1 },
      unique: true
    },
    { name: "product_id_1", key: { product_id: 1 } }
  ],
  payments: [
    { name: "payment_id_1", key: { payment_id: 1 }, unique: true },
    { name: "order_id_1", key: { order_id: 1 }, unique: true }
  ],
  returns: [
    { name: "return_id_1", key: { return_id: 1 }, unique: true },
    { name: "order_id_1", key: { order_id: 1 } }
  ],
  daily_sales: [{ name: "sales_date_1", key: { sales_date: 1 }, unique: true }],
  stream_orders: [
    { name: "order_id_1", key: { order_id: 1 }, unique: true }
  ]
};

const files = [];
files.push(await writeJsonl("collections/customers.jsonl", customers));
files.push(await writeJsonl("collections/products.jsonl", products));
files.push(await writeJsonl("collections/inventory.jsonl", inventory));
files.push(await writeJsonl("collections/orders.jsonl", orders));
files.push(await writeJsonl("collections/order_items.jsonl", orderItems));
files.push(await writeJsonl("collections/payments.jsonl", payments));
files.push(await writeJsonl("collections/returns.jsonl", returns));
files.push(await writeJsonl("collections/daily_sales.jsonl", dailySales));
files.push(await writeJsonl("collections/stream_orders.jsonl", streamOrders));
files.push(await writeJson("cases/transactions.json", transactionCases));
files.push(await writeJson("cases/change-streams.json", changeStreamCases));
files.push(await writeJson("cases/aggregations.json", aggregationCases));
files.push(await writeJson("indexes.json", indexes));

const manifest = {
  dataset: "ecommerce-advanced",
  version: DATASET_VERSION,
  generator: "scripts/generate.mjs",
  seed: SEED,
  generated_at: GENERATED_AT,
  data_epoch: DATA_EPOCH,
  date_encoding: "Extended JSON {$date: ISO-8601}",
  files: files.sort((left, right) => left.path.localeCompare(right.path)),
  collection_counts: {
    customers: customers.length,
    products: products.length,
    inventory: inventory.length,
    orders: orders.length,
    order_items: orderItems.length,
    payments: payments.length,
    returns: returns.length,
    daily_sales: dailySales.length,
    stream_orders: streamOrders.length
  },
  test_case_counts: {
    transactions: transactionCases.length,
    change_streams: changeStreamCases.length,
    aggregations: aggregationCases.length
  },
  empty_output_collections: ["customer_summaries", "stream_events"],
  transaction_fixture_products: {
    commit_purchase: "PROD_0001:WH_EAST",
    concurrent_last_unit: "PROD_0002:WH_EAST",
    insufficient_stock: "PROD_0003:WH_EAST",
    forced_rollback: "PROD_0004:WH_EAST"
  },
  daily_sales: {
    calendar_days: 90,
    stored_days: dailySales.length,
    missing_day_offsets: [...missingSalesDays],
    null_revenue_day_offsets: [...nullRevenueDays]
  }
};

await writeFile(join(outputRoot, "manifest.json"), stableJson(manifest));

const totalBytes = manifest.files.reduce((sum, file) => sum + file.bytes, 0);
console.log(
  JSON.stringify({
    output: outputRoot,
    collections: manifest.collection_counts,
    test_cases: manifest.test_case_counts,
    files: manifest.files.length,
    bytes: totalBytes
  })
);
