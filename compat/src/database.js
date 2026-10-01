import { MongoClient } from "mongodb";

const uri = process.env.MONGODB_URI;

if (!uri) {
  throw new Error("MONGODB_URI is required");
}

export const databaseName =
  process.env.MONGODB_DATABASE || "ecommerce_compat";

// One client and one pool for the process lifetime. TLS, authentication, and
// endpoint differences belong in MONGODB_URI, not in database-specific code.
export const client = new MongoClient(uri, {
  serverSelectionTimeoutMS: 10_000,
  connectTimeoutMS: 10_000,
  socketTimeoutMS: 30_000,
  maxPoolSize: 20
});

export async function withDatabase(operation) {
  await client.connect();
  try {
    return await operation(client.db(databaseName));
  } finally {
    await client.close();
  }
}
