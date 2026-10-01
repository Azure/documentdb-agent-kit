Review the indexes in the Azure DocumentDB database `__DATABASE__` and identify
which ones are redundant and safe to drop.

The database is running locally in the `documentdb-local` container. Connection
settings are in the environment (`DOCUMENTDB_HOST`, `DOCUMENTDB_PORT`,
`DOCUMENTDB_USER`, `DOCUMENTDB_PASSWORD`, `DOCUMENTDB_DATABASE`).

Write your answer to `$OUTPUT_DIR/finding.json`:

```json
{
  "redundant_indexes": ["<index name>", "..."],
  "reason": "why each one is redundant"
}
```

Use the index names as the database reports them. List only indexes that are
genuinely redundant — naming a healthy index is as wrong as missing a redundant
one. State the mechanism for each: an index is not redundant merely because it
is unused today.
