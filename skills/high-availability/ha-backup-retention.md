# ha-backup-retention

**Category:** High Availability & Replication · **Priority:** MEDIUM

## Why it matters

Azure DocumentDB takes **automatic backups** of every cluster continuously and in the background. Backups are stored separately from the source data in a managed storage service, and the process has **no impact on database performance or availability**. Backups are your safety net for accidental deletes, accidental modifications, and application-level corruption — failures that HA and cross-region replicas do **not** protect against (because both replicate the bad change).

Retention is automatic, service-defined, and not customer-configurable:

| Cluster state | Backup retention |
|---|---|
| Active clusters | **35 days** |
| Deleted clusters | **7 days** (then permanently purged) |

Implications:

- **You have 7 days** after deleting a cluster to restore it. After that the backups are gone.
- The deleted-cluster retention window is a **hard platform limit**; you can't extend it.
- HA, cross-region replicas, and backups solve **different** problems. Don't substitute one for another:
  - HA → node/zone failure inside one region.
  - Cross-region replica → regional outage.
  - Backups → logical errors (a user or app deleted/changed something they shouldn't have).

## Incorrect

Treating HA or a cross-region replica as a substitute for backups:

```text
"We have HA + a replica, so we don't need backups."
- HA replicates corruption to the standby synchronously.
- Cross-region replica replicates corruption asynchronously.
- An accidental `db.collection.drop()` is replicated to both.
- Without backups, the data is gone.
```

Letting a deleted cluster sit beyond 7 days expecting backups to still be there:

```text
Day 0:  Cluster deleted (intentionally or accidentally).
Day 8:  Realize the cluster was needed.
Result: Backups permanently purged. Data is unrecoverable.
```

## Correct

- **Treat backups as the recovery tool for logical errors.** When something is accidentally deleted or modified, restore from a point-in-time backup rather than trying to reconstruct from application state.
- **Act fast on accidental cluster deletion.** Initiate restore within the 7-day window for deleted clusters; budget operational headroom for support escalation.
- **Combine all three layers** for production: HA (in-region resilience) + cross-region replica (regional DR) + automatic backups (logical-error recovery).
- **Test restores periodically** — a backup you've never restored from is a backup you don't know works. Validate restore procedures as part of DR drills.

```text
Production-critical Azure DocumentDB topology:
  • HA enabled                        → 99.99% SLA, zone redundancy
  • Cross-region replica              → 99.995% SLA, regional DR
  • Automatic backups (35-day active) → recover from logical errors
  • Tested restore + promotion runbook
```

## References

- [Reliability in Azure DocumentDB — automatic backups & retention](https://learn.microsoft.com/azure/reliability/reliability-documentdb)
- [HA & cross-region replication best practices](https://learn.microsoft.com/azure/documentdb/high-availability-replication-best-practices)
