import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const scenarioRoot = resolve(here, "..");
const dataRoot = resolve(process.argv[2] || join(scenarioRoot, "data"));

function sha256(content) {
  return createHash("sha256").update(content).digest("hex");
}

async function readJson(relativePath) {
  return JSON.parse(await readFile(join(dataRoot, relativePath), "utf8"));
}

async function readJsonl(relativePath) {
  const content = await readFile(join(dataRoot, relativePath), "utf8");
  return content
    .split("\n")
    .filter(Boolean)
    .map((line, index) => {
      try {
        return JSON.parse(line);
      } catch (error) {
        throw new Error(`${relativePath}:${index + 1}: ${error.message}`);
      }
    });
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function unique(rows, field, collection) {
  const values = rows.map((row) => row[field]);
  assert(
    new Set(values).size === values.length,
    `${collection}.${field} contains duplicates`
  );
}

function asDate(value, path) {
  assert(value && typeof value.$date === "string", `${path} is not Extended JSON date`);
  const milliseconds = Date.parse(value.$date);
  assert(Number.isFinite(milliseconds), `${path} is not a valid ISO-8601 date`);
  return milliseconds;
}

const manifest = await readJson("manifest.json");
assert(
  JSON.stringify(manifest.empty_output_collections) ===
    JSON.stringify(["customer_summaries", "stream_events"]),
  "clean output collection list changed"
);

for (const file of manifest.files) {
  const content = await readFile(join(dataRoot, file.path));
  assert(content.length === file.bytes, `${file.path}: byte count changed`);
  assert(sha256(content) === file.sha256, `${file.path}: SHA-256 changed`);
}

const customers = await readJsonl("collections/customers.jsonl");
const products = await readJsonl("collections/products.jsonl");
const inventory = await readJsonl("collections/inventory.jsonl");
const orders = await readJsonl("collections/orders.jsonl");
const orderItems = await readJsonl("collections/order_items.jsonl");
const payments = await readJsonl("collections/payments.jsonl");
const returns = await readJsonl("collections/returns.jsonl");
const dailySales = await readJsonl("collections/daily_sales.jsonl");
const streamOrders = await readJsonl("collections/stream_orders.jsonl");
const transactionCases = await readJson("cases/transactions.json");
const changeStreamCases = await readJson("cases/change-streams.json");
const aggregationCases = await readJson("cases/aggregations.json");
const indexes = await readJson("indexes.json");

const collections = {
  customers,
  products,
  inventory,
  orders,
  order_items: orderItems,
  payments,
  returns,
  daily_sales: dailySales,
  stream_orders: streamOrders
};

for (const [name, expected] of Object.entries(manifest.collection_counts)) {
  assert(collections[name].length === expected, `${name}: expected ${expected} records`);
}

unique(customers, "customer_id", "customers");
unique(products, "product_id", "products");
unique(inventory, "inventory_id", "inventory");
unique(orders, "order_id", "orders");
unique(orderItems, "order_item_id", "order_items");
unique(payments, "payment_id", "payments");
unique(returns, "return_id", "returns");
unique(streamOrders, "order_id", "stream_orders");

const customerIds = new Set(customers.map((row) => row.customer_id));
const productIds = new Set(products.map((row) => row.product_id));
const orderIds = new Set(orders.map((row) => row.order_id));

for (const order of orders) {
  assert(customerIds.has(order.customer_id), `orders: missing customer ${order.customer_id}`);
  asDate(order.placed_at, `${order.order_id}.placed_at`);
  asDate(order.updated_at, `${order.order_id}.updated_at`);
}

for (const item of orderItems) {
  assert(orderIds.has(item.order_id), `order_items: missing order ${item.order_id}`);
  assert(productIds.has(item.product_id), `order_items: missing product ${item.product_id}`);
}

for (const payment of payments) {
  assert(orderIds.has(payment.order_id), `payments: missing order ${payment.order_id}`);
  assert(
    customerIds.has(payment.customer_id),
    `payments: missing customer ${payment.customer_id}`
  );
}

for (const returnRow of returns) {
  assert(orderIds.has(returnRow.order_id), `returns: missing order ${returnRow.order_id}`);
  assert(
    customerIds.has(returnRow.customer_id),
    `returns: missing customer ${returnRow.customer_id}`
  );
  assert(
    productIds.has(returnRow.product_id),
    `returns: missing product ${returnRow.product_id}`
  );
}

for (const row of inventory) {
  assert(productIds.has(row.product_id), `inventory: missing product ${row.product_id}`);
  assert(row.quantity >= 0 && row.reserved >= 0, `${row.inventory_id}: negative stock`);
  assert(row.reserved <= row.quantity, `${row.inventory_id}: reserved exceeds quantity`);
}

const itemsByOrder = new Map();
for (const item of orderItems) {
  const items = itemsByOrder.get(item.order_id) || [];
  items.push(item);
  itemsByOrder.set(item.order_id, items);
}

const paymentsByOrder = new Map(payments.map((payment) => [payment.order_id, payment]));
for (const order of orders) {
  const items = itemsByOrder.get(order.order_id) || [];
  const itemTotal = Math.round(
    items.reduce((sum, item) => sum + item.line_total, 0) * 100
  ) / 100;
  assert(items.length === order.item_count, `${order.order_id}: item_count mismatch`);
  assert(itemTotal === order.total_amount, `${order.order_id}: total mismatch`);
  assert(
    paymentsByOrder.get(order.order_id)?.amount === order.total_amount,
    `${order.order_id}: payment amount mismatch`
  );
}

const inventoryById = new Map(inventory.map((row) => [row.inventory_id, row]));
for (const testCase of transactionCases) {
  const key = `${testCase.product_id}:${testCase.warehouse_id}`;
  const row = inventoryById.get(key);
  assert(row, `${testCase.case_id}: inventory fixture ${key} missing`);
  assert(
    row.quantity === testCase.initial_quantity,
    `${testCase.case_id}: expected initial quantity ${testCase.initial_quantity}, got ${row.quantity}`
  );
}

assert(
  transactionCases.find((testCase) => testCase.case_id === "concurrent-last-unit")
    ?.expected_commits === 1,
  "concurrent transaction case must require exactly one commit"
);

assert(changeStreamCases.length === 4, "expected four change-stream operations");
assert(
  changeStreamCases.map((testCase) => testCase.operation).join(",") ===
    "insert,update,replace,delete",
  "change-stream operation sequence changed"
);

const salesDates = dailySales.map((row, index) =>
  asDate(row.sales_date, `daily_sales[${index}].sales_date`)
);
assert(new Set(salesDates).size === salesDates.length, "daily_sales dates are not unique");
const dataEpoch = Date.parse(manifest.data_epoch);
const storedDayOffsets = new Set(
  salesDates.map((date) => Math.round((date - dataEpoch) / 86_400_000))
);
const actualMissingDayOffsets = Array.from(
  { length: manifest.daily_sales.calendar_days },
  (_, day) => day
).filter((day) => !storedDayOffsets.has(day));
assert(
  JSON.stringify(actualMissingDayOffsets) ===
    JSON.stringify(manifest.daily_sales.missing_day_offsets),
  "daily_sales missing-day offsets changed"
);
const actualNullRevenueOffsets = dailySales
  .filter((row) => row.revenue === null)
  .map((row) =>
    Math.round((Date.parse(row.sales_date.$date) - dataEpoch) / 86_400_000)
  );
assert(
  JSON.stringify(actualNullRevenueOffsets) ===
    JSON.stringify(manifest.daily_sales.null_revenue_day_offsets),
  "daily_sales null-revenue offsets changed"
);
assert(
  dailySales.filter((row) => row.revenue === null).length ===
    manifest.daily_sales.null_revenue_day_offsets.length,
  "daily_sales null-revenue fixture count changed"
);
assert(
  manifest.daily_sales.calendar_days - dailySales.length ===
    manifest.daily_sales.missing_day_offsets.length,
  "daily_sales missing-day fixture count changed"
);

const requiredAdvancedStages = new Set([
  "$facet",
  "$lookup",
  "$expr",
  "$setWindowFields",
  "$densify",
  "$fill",
  "$unionWith",
  "$bucket",
  "$sortArray",
  "$merge"
]);
const documentedStages = new Set(
  aggregationCases.flatMap((testCase) => testCase.stages)
);
for (const stage of requiredAdvancedStages) {
  assert(documentedStages.has(stage), `advanced aggregation case missing ${stage}`);
}

for (const collection of Object.keys(collections)) {
  assert(indexes[collection], `indexes.json has no entry for ${collection}`);
}

assert(
  manifest.test_case_counts.transactions === transactionCases.length &&
    manifest.test_case_counts.change_streams === changeStreamCases.length &&
    manifest.test_case_counts.aggregations === aggregationCases.length,
  "test case counts changed"
);

console.log(
  JSON.stringify({
    status: "PASS",
    dataset: manifest.dataset,
    version: manifest.version,
    files_verified: manifest.files.length + 1,
    collection_counts: manifest.collection_counts,
    test_case_counts: manifest.test_case_counts,
    invariants: {
      foreign_keys: "PASS",
      order_totals: "PASS",
      payment_totals: "PASS",
      time_series_gaps: "PASS",
      transaction_fixtures: "PASS",
      change_stream_sequence: "PASS",
      advanced_aggregation_coverage: "PASS",
      hashes: "PASS"
    }
  })
);
