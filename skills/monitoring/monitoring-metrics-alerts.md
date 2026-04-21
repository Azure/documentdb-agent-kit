# monitoring-metrics-alerts

**Category:** Monitoring & Diagnostics · **Priority:** MEDIUM

## Why it matters

Cluster-level saturation (CPU, memory, IOPS, storage, connections) causes tail-latency spikes long before outright failure. Alerting early on the **right leading indicators** — sized for the chosen M-tier — lets you scale up or investigate before users notice.

Minimum recommended alerts:

| Metric | Suggested threshold | Why |
|---|---|---|
| CPU % (per node) | > 75% sustained 10 min | Approaching vertical limit |
| Memory (working set) | > 80% of RAM | Index / vector pages about to swap |
| Storage used | > 80% of provisioned | Time to grow or shard |
| IOPS used | > 80% of tier limit | IOPS saturation drives latency |
| Connection count | > 80% of tier limit | Driver pool or leak |
| Failed connections | > 0 sustained | Auth / TLS / networking issue |
| Replication lag (cross-region) | > expected baseline × 2 | DR posture degraded |

## Incorrect

```text
Alerts configured: none
Incident detection: customer tickets
```

## Correct

Codify alerts in Bicep/Terraform alongside the cluster so they ship with every environment, and route to an on-call channel (Teams, PagerDuty, etc.).

```bicep
// sketch — confirm metric names in Azure Monitor for Azure DocumentDB
resource cpuAlert 'Microsoft.Insights/metricAlerts@...' = {
  name: 'ddb-cpu-high'
  properties: {
    scopes: [ ddb.id ]
    criteria: {
      allOf: [ {
        metricName: 'cpu_percent'
        operator: 'GreaterThan'
        threshold: 75
        timeAggregation: 'Average'
      } ]
    }
    windowSize: 'PT10M'
    evaluationFrequency: 'PT1M'
    severity: 2
  }
}
```

Pair metric alerts with the slow-query log workflow (`monitoring-slow-query-log`) so you have both leading (saturation) and diagnostic (which query) signals.

## References

- [Monitor Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/)
