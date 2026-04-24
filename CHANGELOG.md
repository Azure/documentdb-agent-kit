# Changelog

## 2026-04-21 — `full-text-search`: corrected to `createSearchIndexes` + `$search` syntax; added analyzer rules

Previous rules documented the community MongoDB shape (`createIndexes` with `{ field: "textSearch" }` keys and a `count` field inside `$search`). Azure DocumentDB full-text search actually uses:

- `runCommand({ createSearchIndexes: "<col>", indexes: [{ name, definition: { mappings: { dynamic, fields }, analyzers? } }] })` for index creation
- `$search: { index: "<name>", text|phrase: { query, path } }` + a downstream `{ $limit: N }` stage (no `count` field)
- Index names referenced explicitly in `$search` because the engine does not auto-pick when multiple exist

Rule changes:

- Renamed `fts-create-textsearch-index.md` → **`fts-create-search-index.md`**; rewrote with `createSearchIndexes` / `definition.mappings` and `dynamic: false` guidance.
- Rewrote `fts-basic-search.md`, `fts-fuzzy-search.md`, `fts-phrase-search.md`, `fts-hybrid-search.md` to use the correct syntax (no `count`, uses `$limit`, specifies `index`).
- New **`fts-custom-analyzers.md`** — index-time `edgeGram` + search-time plain `keyword` analyzer pair for case-insensitive prefix matching on SKUs / part numbers / codes, with `lowerCase` + `asciiFolding` token filter ordering.
- New **`fts-path-hierarchy.md`** — `pathHierarchy` tokenizer for hierarchical identifiers (`BN-747-ENG-2024.05`, dotted paths, slash paths).
- New **`fts-multifield-index.md`** — single search index mapping multiple ID-like fields; fan-out-and-merge pattern while `$search` `compound` (`should` / `minimumShouldMatch`) is not yet supported.
- Updated SKILL.md front-matter and rule list; expanded the top-level README FTS row to reflect the broader surface.
- Fixed cross-references using the old syntax elsewhere in the kit: `skills/indexing/index-text-prefer-textsearch.md` (rewrote to use `createSearchIndexes`; refreshed related-rules links), `skills/indexing/index-pattern-cookbook.md` (recipe 14 now uses `createSearchIndexes` + `$limit`), `skills/query-optimizer/references/core-indexing-principles.md` (table + special-indexes section), and `AGENTS.md` (skill row + intro sentence).

## 2026-04-21 — `azure-deployment`: interactive subscription / RG / region pickers

- `SKILL.md` now requires the agent to **list subscriptions first, then resource groups, then regions** (only if creating a new RG). These are now Steps 1, 2, and 3; the remaining cluster inputs moved to Step 4 and deployment paths to Step 6. The previous single "gather inputs" table collapsed these into one prompt, which made agents silently assume the active subscription.
- `examples/azure-deployment/deploy.sh` and `deploy.ps1` implement the same flow interactively:
  1. Ensure `az` is installed and signed in
  2. List enabled subscriptions; auto-pick when there's only one, otherwise prompt
  3. Register the `Microsoft.DocumentDB` provider on the chosen subscription
  4. List existing resource groups (+ an explicit "create new" menu entry); derive location from the chosen RG when reusing
  5. Only prompt for a region if creating a new RG, using the `mongoClusters`-supported list
  6. Summarise defaults, confirm, deploy
- Both scripts now accept **zero positional arguments** (`./deploy.sh`) for fully interactive runs; passing `<rg> <location> [params-file]` still works and skips the relevant pickers.

## 2026-04-21 — `azure-deployment`: production-safe defaults (M30 + ZoneRedundant HA + 128 GiB) with dev parameters file and confirmation prompt

## 2026-04-21 — Added `documentdb-azure-deployment` skill

- New `skills/azure-deployment/` interactive workflow skill for provisioning an Azure DocumentDB cluster end-to-end. Grounded in Microsoft Learn docs for `Microsoft.DocumentDB/mongoClusters` (API `2025-09-01`).
- `SKILL.md` walks the agent through: a **Step 0 preflight loop** (CLI installed, signed in, correct subscription, `Microsoft.DocumentDB` registered, caller has Contributor/Owner, region supports `mongoClusters`), input gathering (tier, storage, HA, firewall posture), choosing a deployment path (Bicep / CLI one-shot / Terraform / portal), deployment, verification, connection-string retrieval, firewall / Private Endpoint posture, and teardown.
- `references/bicep-cluster-template.md` contains the canonical parameterized `main.bicep` with `@allowed` tier list, Key Vault password reference example, and an optional Private Endpoint variant (`publicNetworkAccess: 'Disabled'` + `Microsoft.Network/privateEndpoints` with group `MongoCluster`).
- New `examples/azure-deployment/` — a no-agent ready-to-run copy: `main.bicep`, `main.parameters.sample.json` (with Key Vault secret reference), `deploy.sh` (bash + preflight checks + auto-registers provider + creates RG), `deploy.ps1` (PowerShell equivalent), and `README.md`. Lets customers clone the repo and `./deploy.sh <rg> <location>` without involving any agent.
- Registered in `AGENTS.md` (skills table + routing hint) and `README.md`. Validator passes: 16 skills, unique names.

## 2026-04-21 — Added `documentdb-indexing` rule-folder skill

- New `skills/indexing/` skill (11 rules) dedicated to **index-type selection and shape** — answers "which index should I create?", complementing `documentdb-query-optimizer` (which answers "why is my query slow?").
- Rules: `index-single-field`, `index-compound-esr` (with DocumentDB's 32-field compound limit and the prefix rule), `index-multikey-arrays` (parallel-array restriction, `$elemMatch`, no covered queries), `index-text-prefer-textsearch` (prefer DocumentDB `textSearch` over community `$text`), `index-wildcard-dynamic-schemas`, `index-hashed-shard-keys`, `index-2dsphere-geospatial` (`[lng, lat]` order), `index-ttl-expiry` (Date field, single-field only, ~60s sweeper lag), `index-count-budget` (5–15 per collection), `index-lifecycle-drop-hide` (`$indexStats` → `hideIndex` → `dropIndex`, redundancy detection, `_id` cannot be dropped), `index-pattern-cookbook` (16 query-pattern → index-shape recipes).
- Registered skill in `AGENTS.md` (skills table + routing hint) and `README.md` (rule-folder skills table).

## 2026-04-21 — Cross-tool compatibility pass

- Added a `SKILL.md` with `name` + `description` YAML front matter to every rule-folder skill (`data-modeling`, `cluster-sharding`, `query-optimization`, `driver`, `vector-search`, `full-text-search`, `high-availability`, `security`, `monitoring`, `local-deployment`). All 14 skills are now discoverable by Agent Skills–compatible tools.
- Rewrote `AGENTS.md` as a proper skills index with a "how agents should use this kit" section, a full skills table (rule collections + interactive skills), and routing hints mapping user intents to skills.
- Added per-tool install instructions to `README.md` (Claude Code project + user scope, GitHub Copilot, Gemini CLI).
- Added `scripts/validate-skills.ps1` — verifies every `skills/*/SKILL.md` has valid front matter with non-empty `name` and `description`, and that names are unique across the kit.

## 2026-04-21 — Merged `indexing/` rules into `query-optimizer/references/`

- Moved `skills/indexing/index-support-queries.md` into `skills/query-optimizer/references/`.
- Removed the standalone `skills/indexing/` rule folder — compound-index guidance now lives with the query-optimizer skill that loads it.
- Added `skills/query-optimizer/references/core-indexing-principles.md` — the deep-dive referenced from the skill's `SKILL.md` (supported index types, ESR rule, reading `explain("executionStats")`, covered queries, common diagnoses, anti-patterns, special index categories, verification workflow).
- Updated `README.md` to reflect both rule-folder and standalone-SKILL.md skill types.

## 2026-04-21 — Flattened skill layout

- Removed the `skills/documentdb-best-practices/` wrapper and the intermediate `rules/` folder.
- Every category folder (`data-modeling`, `cluster-sharding`, `indexing`, `query-optimization`, `driver`, `vector-search`, `full-text-search`, `high-availability`, `security`, `monitoring`, `local-deployment`) now lives directly under `skills/`.
- Updated top-level `README.md` and `AGENTS.md` to reference the new paths.
- No rule files were renamed or modified.

## 2026-04-22 — Added Local Deployment category

- New `rules/local-deployment/` folder with 7 best-practice rules for running DocumentDB locally: choosing the right image (Gateway vs psql vs source), `docker-compose.yml` patterns, TLS + SCRAM connection config, env-driven configuration (`DOCUMENTDB_URI`, `DOCUMENTDB_ALLOW_INVALID_CERTS`), sample-data management (`SKIP_INIT_DATA` / `INIT_DATA_PATH`), port bindings (`127.0.0.1` only), and local/production parity via versioned index & seed scripts.
- Registered the new category in `SKILL.md`, `metadata.json`, and the skill README.

## 2026-04-22 — Added Full-Text Search category

- New `rules/full-text-search/` folder with 5 rules covering the `textSearch` index type and the `$search` aggregation stage: index creation, BM25 keyword search, fuzzy search (`maxEdits`), phrase search (`slop`), and hybrid (BM25 + vector) search via Reciprocal Rank Fusion.
- Registered the new category in `SKILL.md`, `metadata.json`, and the skill README.

## 2026-04-22 — Grouped rules into category subfolders

- Rules are now organized one folder per category under `rules/` (e.g. `rules/vector-search/`, `rules/cluster-sharding/`, `rules/security/`).
- Updated SKILL.md links accordingly. File names (and rule prefixes) are unchanged.

## 2026-04-21 — Retargeted to Azure DocumentDB (v0.2.0)

- Kit now targets **Azure DocumentDB (with MongoDB compatibility)** — the managed service built on the open-source DocumentDB project.
- Rewrote Sharding rules around DocumentDB's sharding model (shard key not required until terabytes).
- Rewrote Vector rules to reflect DocumentDB's `cosmosSearch` with **DiskANN** (recommended), HNSW, and IVF; added Product Quantization and Half-Precision indexing rules.
- Updated HA rules with the documented SLAs (99.99% HA, 99.995% HA + cross-region replica).
- Removed Full-Text Search category (not a first-class DocumentDB feature).

## 2026-04-21 — Initial scaffold (v0.1.0)

- Created `documentdb-best-practices` skill targeting Cosmos DB for MongoDB vCore (later retargeted).
