# Contributing

Thanks for helping improve the documentdb-agent-kit!

## Adding a rule

1. Pick a category and use its prefix (e.g., `shard-`, `query-`, `driver-`).
2. Create a file in `skills/documentdb-best-practices/rules/<prefix>-<slug>.md`.
3. Follow the rule template:
   - **Why it matters** — one short paragraph
   - **Incorrect** — code example + explanation
   - **Correct** — code example + explanation
   - **References** — links to official docs
4. Add the rule to the category index in `skills/documentdb-best-practices/SKILL.md`.
5. Bump the version in `skills/documentdb-best-practices/metadata.json`.

## Rule style

- Be specific and actionable; avoid generic MongoDB advice unless it materially applies to Cosmos DB for MongoDB vCore.
- Prefer examples in JavaScript/Node, Python, and C# where reasonable.
- Mark vCore-specific behavior explicitly (e.g., `cosmosSearch`, cluster tiers, HA model).

## PRs

Small focused PRs are preferred. Add a CHANGELOG entry for each merged PR.
