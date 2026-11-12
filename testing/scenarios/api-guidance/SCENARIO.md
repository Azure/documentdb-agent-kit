# API guidance example contracts

This infrastructure-free scenario executes **the marked JavaScript code blocks from the rules**, rather than a second copy of their implementation:

- `skills/driver/driver-validate-api-inputs.md`: defaults only on omission, complete safe integer/scalar/date validation, no write callback on invalid input, sanitized parser-error classification.
- `skills/indexing/index-keyset-pagination.md`: scope-preserving lexicographic timestamp/id filter, last-returned-row continuation, complete tie traversal, and newly inserted records on either side of the cursor.

Run `node --test testing/scenarios/api-guidance/test-snippets.cjs` from the repository root, or `python -m pytest scenarios/api-guidance` from `testing/` with the test dependencies installed. The thin Python wrapper integrates with the existing scenario runner; it skips explicitly if Node is missing. Infrastructure-free CI installs Node 22 so this contract does not silently skip there.

The Node checks require only built-in modules, no npm dependencies, database, network, credentials or model calls. The example VM receives no process, filesystem, network or package-import helpers. In-memory collection fixtures verify emitted filters and page logic; they are not MongoDB/BSON execution or query-plan proof. Parser classification checks are not a real Express request test.

These regression checks guard the written examples, not model behavior. They do not prove that the kit caused or fixes an agent's generated-code errors, that a new agent run uses these rules, or that a generated application passes managed Azure acceptance. Such claims require separate live or controlled skill-efficacy evaluations.
