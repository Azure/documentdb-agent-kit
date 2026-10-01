# Results — route efficiency

Same contract as [`../../documentdb-sdk-skills/results/`](../../documentdb-sdk-skills/results/):
curated artifacts committed, raw runs gitignored, provenance mandatory.

## Naming

```
<date>-route-efficiency.json    the aggregated comparison
<date>-route-efficiency.md      the rendered report
raw/                            per-run output — GITIGNORED
```

Unlike the SDK-skills benchmark there is no `-treatment` / `-control` file
split: both arms are aggregated into one artifact by `summarize.py`, which
cannot produce a report from a single arm.

## Generating

```bash
export DB_PASSWORD='<your-password>'
export AGENT_CMD='copilot --allow-all-tools -p "$PROMPT"'

bash ../run-comparison.sh --iterations 5
python3 ../summarize.py raw --out "$(date -u +%F)-route-efficiency.md"
python3 ../summarize.py raw --json > "$(date -u +%F)-route-efficiency.json"
```

## What is here now

**Nothing.** No agent run has been executed — that needs model credentials. The
harness, arms, fixture and parity grader are built and validated; see
[`../README.md`](../README.md).

