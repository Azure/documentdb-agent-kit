# Prompt

Create a small Node.js e-commerce project for Azure DocumentDB using the
official `mongodb` driver.

- Read the connection from `MONGODB_URI`.
- Reuse one `MongoClient`.
- Seed deterministic `customers`, `products`, `orders`, `order_items`, and
  `inventory` collections.
- Add one filtered `find()` query and three `$lookup` queries.
- Add `npm test` with exact expected results.
- Do not hardcode credentials or add database-specific branches.
