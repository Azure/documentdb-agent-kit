# storage-tier-iops-caps

**Category:** Storage · **Priority:** HIGH

## Why it matters

On Premium SSD v2, the **compute tier — not the disk size — sets the maximum sustainable IOPS and bandwidth.** Azure DocumentDB auto-configures the cluster to the upper-bound values for the chosen tier at no added cost. This means under-sizing compute will silently cap your I/O throughput even if the disk could deliver more, and over-sizing the disk does nothing for IOPS.

## IOPS and bandwidth caps (Premium SSD v2)

| Compute tier | Cores | Max IOPS | Max bandwidth (MBps) |
|---|---:|---:|---:|
| M30  | 2  | 3,750  | 85    |
| M40  | 4  | 6,400  | 145   |
| M50  | 8  | 12,800 | 290   |
| M60  | 16 | 25,600 | 600   |
| M80  | 32 | 51,200 | 865   |
| M200 | 64 | 80,000 | 1,200 |

Read these as **ceilings, not guarantees** — actual throughput depends on workload shape (read/write mix, doc size, index pressure). If your monitoring shows you're pegged at the tier's IOPS or MBps cap, scale up compute; growing the disk will not help.

## Sizing workflow

1. Estimate **data volume** (current + 12-month growth). Pick `storage.sizeGb` for capacity only.
2. Estimate **peak IOPS and MBps** from the workload (use existing cluster metrics if migrating).
3. Pick the **smallest compute tier** whose caps in the table above cover the peak.
4. Set `storage.type = 'PremiumSSDv2'`. No further IOPS tuning required.

## Incorrect

Choosing the storage size to "unlock" IOPS:

```bicep
// Wrong mental model — Premium SSD v2 IOPS are gated by compute, not disk.
storage: {
  sizeGb: 4096           // sized to chase IOPS, not capacity
  type: 'PremiumSSDv2'
}
compute: {
  tier: 'M30'            // still capped at 3,750 IOPS regardless of disk size
}
```

## Correct

```bicep
// Workload: ~10k peak IOPS, ~250 MBps, ~150 GB data.
storage: {
  sizeGb: 256            // capacity headroom for growth
  type: 'PremiumSSDv2'
}
compute: {
  tier: 'M50'            // 12,800 IOPS / 290 MBps cap — covers peak with headroom
}
```

Monitor IOPS and bandwidth from the cluster's **Metrics** blade; if you consistently hit the tier cap, scale compute up one step (M50 → M60 doubles IOPS to 25,600).

## References

- [Premium SSD v2 disks — Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/high-performance-storage)
