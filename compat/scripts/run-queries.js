import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import { withDatabase } from "../src/database.js";
import { runQueries } from "../src/queries.js";

const result = await withDatabase(runQueries);
const json = `${JSON.stringify(result, null, 2)}\n`;

if (process.env.RESULT_FILE) {
  await mkdir(dirname(process.env.RESULT_FILE), { recursive: true });
  await writeFile(process.env.RESULT_FILE, json);
}

process.stdout.write(json);
