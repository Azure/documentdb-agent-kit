import { readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { MongoClient } from "mongodb";

const uri = process.env.MONGODB_URI;
if (!uri) throw new Error("MONGODB_URI is required");

const databaseName = process.env.MONGODB_DATABASE || "ecommerce_advanced";
const here = dirname(fileURLToPath(import.meta.url));
const dataRoot = resolve(here, "..", "data");

function reviveExtendedJson(value) {
  if (Array.isArray(value)) return value.map(reviveExtendedJson);
  if (value && typeof value === "object") {
    if (
      Object.keys(value).length === 1 &&
      typeof value.$date === "string"
    ) {
      return new Date(value.$date);
    }
    return Object.fromEntries(
      Object.entries(value).map(([key, nested]) => [
        key,
        reviveExtendedJson(nested)
      ])
    );
  }
  return value;
}

async function readJson(relativePath) {
  return JSON.parse(await readFile(join(dataRoot, relativePath), "utf8"));
}

async function readJsonl(relativePath) {
  const content = await readFile(join(dataRoot, relativePath), "utf8");
  return content
    .split("\n")
    .filter(Boolean)
    .map((line) => reviveExtendedJson(JSON.parse(line)));
}

const manifest = await readJson("manifest.json");
const indexes = await readJson("indexes.json");
const client = new MongoClient(uri, {
  serverSelectionTimeoutMS: 10_000,
  connectTimeoutMS: 10_000,
  socketTimeoutMS: 60_000,
  maxPoolSize: 10
});

await client.connect();
try {
  const db = client.db(databaseName);

  // Remove write-producing test outputs from earlier runs. Dataset loading must
  // restore a clean baseline, not leave $merge or change-stream artifacts.
  for (const collectionName of manifest.empty_output_collections || []) {
    await db.collection(collectionName).drop().catch((error) => {
      if (error.codeName !== "NamespaceNotFound") throw error;
    });
  }

  for (const [collectionName, count] of Object.entries(
    manifest.collection_counts
  )) {
    await db.collection(collectionName).drop().catch((error) => {
      if (error.codeName !== "NamespaceNotFound") throw error;
    });
    const collection = db.collection(collectionName);
    const rows = await readJsonl(`collections/${collectionName}.jsonl`);
    if (rows.length) {
      await collection.insertMany(rows, { ordered: true });
    }

    for (const index of indexes[collectionName] || []) {
      const { key, ...options } = index;
      await collection.createIndex(key, options);
    }

    const actual = await collection.countDocuments();
    if (actual !== count) {
      throw new Error(
        `${collectionName}: loaded ${actual} records, expected ${count}`
      );
    }
    console.log(`${collectionName}: ${actual}`);
  }

  console.log(
    JSON.stringify({
      status: "PASS",
      database: databaseName,
      dataset: manifest.dataset,
      version: manifest.version
    })
  );
} finally {
  await client.close();
}
