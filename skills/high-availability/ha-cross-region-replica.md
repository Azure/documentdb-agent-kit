# ha-cross-region-replica

**Category:** High Availability & Replication · **Priority:** MEDIUM

## Why it matters

Azure DocumentDB supports **active-passive cross-region replication**: one cluster is the read-write primary, a replica cluster in another region stays read-only and in sync. If a region fails, the replica can be promoted to take writes with minimal interruption. Combined with in-region HA, this delivers the **99.995% SLA** and enables:
- Disaster recovery across regions.
- Read-scale offload to the replica for heavy analytical reads or for region-local reads close to distant users.

Three things to internalize before designing for cross-region:

- **Replication is asynchronous.** Replica reads are eventually consistent — writes acknowledged on the primary may not yet be visible on the replica. Applications that need read-your-own-writes must route those reads to the primary.
- **Regional promotion has a non-zero RPO.** Because replication is asynchronous, recent writes that haven't yet been delivered to the replica are **lost** when the replica is promoted during a regional outage. Replication lag depends on the primary's write intensity and overall cluster load — monitor lag and size both clusters to keep it bounded.
- **Failover is *not* automatic across regions.** Per the Azure shared-responsibility model, you (the customer) own the DR plan. Region failover requires a **customer-triggered promotion** of the replica. In-region HA failover is automatic; cross-region promotion is not.

A canonical read-routing pattern:

- **OLTP / transactional reads + all writes** → primary cluster (strong consistency).
- **OLAP / analytical / reporting reads** → replica cluster (eventual consistency, but offloads the primary).

## Incorrect

Relying solely on in-region HA for a mission-critical global application:

```text
Single-region cluster, HA: on
- Survives node and zone failures (good)
- Does NOT survive regional outage
- No automatic cross-region failover
- No read-scale offload for distant users
```

## Correct

Pair HA + cross-region replica for production-critical workloads:

1. Enable HA on the primary cluster (see `ha-enable-for-production`).
2. Create a replica cluster (`createMode: 'GeoReplica'`) in a paired or geographically near region. The replica reuses the primary's admin credentials, databases, collections, and documents — only the cluster name and region differ.
3. Enable HA on the replica too — required for the combined 99.995% SLA and for AZ placement after promotion.
4. Route latency-sensitive reads in that region to the replica's connection string (read-only).
5. Document and **periodically test** a promotion runbook for DR (see the [Promotion (DR failover) — runbook](#promotion-dr-failover--runbook) section below).

```text
Primary:   East US 2  (read-write, HA on)
Replica:   West US 3  (read-only,  HA on)
Combined SLA: 99.995%
```

Design for eventual consistency on the replica; writes must still target the primary until you explicitly promote the replica.

### Cross-region vs same-region replicas

The same replica mechanism supports two distinct deployment shapes — pick the one that matches the goal:

| Replica region | Use case | DR benefit | Read scale-out |
|---|---|---|---|
| **Different region** from primary | DR + read scale-out for users in another geography | ✅ Survives a regional outage | ✅ Region-local reads near distant users |
| **Same region** as primary | Pure read scale-out (e.g. heavy analytics or reporting workload offload) | ❌ Both clusters share regional fate | ✅ Same-zone or cross-zone reads inside one region |

Same-region replicas use the identical control-plane flow (`createMode: 'GeoReplica'`, `replicaParameters` pointing at the source), with the replica `location` set equal to the primary's. They are **not** a DR strategy on their own.

> ⚠️ **One replica per primary.** Azure DocumentDB allows **only one replica cluster per primary**. Picking a same-region replica means you cannot also have a cross-region DR replica — it's a trade-off, not an addition. If you need both regional DR and same-region read offload, pick the cross-region replica and offload analytics to it (accepting cross-region read latency), or design the primary cluster to absorb the read load.

### Region selection

Pick the replica region with three trade-offs in mind:

| Factor | Guidance |
|---|---|
| **Network latency from primary to replica** | Closer regions = lower replication lag. Prefer geographically near regions when reads from the replica must be near-fresh. |
| **Write-path latency on the primary** | Asynchronous replication does not block writes, but cross-region traffic still costs egress and adds operational risk. Don't over-replicate "just in case." |
| **DR isolation** | The replica must be in a **different region** from the primary to survive a regional outage. For paired-region semantics, prefer an Azure region pair. |
| **Read-locality** | If the goal is read scale-out for users in a specific geography, pick the region nearest those users — not the one nearest the primary. |

### Read scale-out routing

Use two connection strings in the application:

- **Writes & strongly-consistent reads** → primary cluster connection string (use the **Global read-write** hostname `<cluster>.global.mongocluster.cosmos.azure.com` so it auto-follows promotion).
- **Region-local / analytical reads** → replica's read-only connection string.

This is the only way to offload reads; there is no implicit read-routing in the driver. Document which queries are safe to route to the replica and which require the primary.

### Bicep — replica cluster

The replica is a separate `Microsoft.DocumentDB/mongoClusters` resource with `createMode: 'GeoReplica'` and a `replicaParameters` block that points at the primary's resource ID and location. Most data-plane fields (admin, server version, sharding, storage, compute) are inherited from the source and **must not** be set on the replica.

```bicep
@description('Resource ID of the primary (source) cluster.')
param primaryClusterId string

@description('Azure region of the primary cluster.')
param primaryLocation string

@description('Azure region for the replica cluster (different from the primary for cross-region DR).')
param replicaLocation string

@description('Globally unique replica cluster name.')
param replicaClusterName string

resource replica 'Microsoft.DocumentDB/mongoClusters@2025-09-01' = {
  name:     replicaClusterName
  location: replicaLocation
  properties: {
    createMode: 'GeoReplica'
    replicaParameters: {
      sourceResourceId: primaryClusterId
      sourceLocation:   primaryLocation
    }
    // Recommended: enable HA on the replica too for the 99.995% combined SLA.
    highAvailability: {
      targetMode: 'ZoneRedundantPreferred'
    }
  }
}

output replicaId string = replica.id
```

Deploy after the primary exists (the API requires the source cluster to be in a ready state):

```bash
az deployment group create \
  --resource-group rg-docdb-replica \
  --template-file replica.bicep \
  --parameters \
      primaryClusterId="/subscriptions/<sub>/resourceGroups/rg-docdb-prod/providers/Microsoft.DocumentDB/mongoClusters/docdb-prod-001" \
      primaryLocation=eastus2 \
      replicaLocation=westus3 \
      replicaClusterName=docdb-prod-001-replica
```

The replica may be deployed into a **different resource group** (and even a different region's RG) than the primary in IaC; only `sourceResourceId` and `sourceLocation` matter for linkage. (Portal-initiated replica creation during primary provisioning places it in the same subscription + RG as the primary — see the lifecycle section below.)

### Terraform — replica cluster

Requires AzureRM provider **4.15+** (earlier 4.x versions reject `create_mode = "GeoReplica"`). With `GeoReplica`, the data-plane attributes (`administrator_*`, `compute_tier`, `shard_count`, `storage_size_in_gb`, `version`) are inherited from the source and should be omitted.

```hcl
resource "azurerm_mongo_cluster" "replica" {
  name                = "docdb-prod-001-replica"
  resource_group_name = azurerm_resource_group.replica_rg.name
  location            = "westus3"

  create_mode      = "GeoReplica"
  source_server_id = azurerm_mongo_cluster.primary.id
  source_location  = azurerm_mongo_cluster.primary.location

  high_availability_mode = "ZoneRedundantPreferred"   # combined 99.995% SLA
}
```

If the replica is in a separate Terraform state, hard-code `source_server_id` and `source_location` (or read them via an `azurerm_mongo_cluster` data source) instead of referencing the resource directly.

### Promotion (DR failover) — runbook

Promotion is a control-plane action (REST / portal); there is no IaC primitive for it. After promotion, the former replica becomes a standalone read-write cluster. The full operational checklist:

1. **Trigger promotion** from the Azure portal: select the replica → **Settings → Global distribution → Promote**, confirm the cluster name. (Equivalent REST call available via `az rest`.) During promotion, the **Global read-write** connection string is automatically updated to point at the newly promoted cluster, and **the ex-primary is automatically reconfigured as the new replica (read-only)** of the promoted cluster. This means you can "fail back" later by promoting the original cluster again — no need to recreate the replication relationship.
2. **Re-enable HA on the promoted cluster.** HA is **not** carried over automatically — once the former replica becomes the new primary, set `highAvailability.targetMode` to `ZoneRedundantPreferred` so the promoted cluster regains the 99.99% in-region SLA.
3. **Update application connection strings.** Behavior depends on which string the app uses:
   - **Global read-write** (`<cluster>.global.mongocluster.cosmos.azure.com` on the original primary) — keeps working; it auto-routes to the new write region after promotion. **Use this in apps to avoid post-promotion code changes.**
   - **Self / cluster-specific** of the old primary — becomes read-only. Apps that wrote through it must be repointed to the new primary's self connection string (or to the Global RW string).
   - **Self of the former replica** — still valid; the cluster is now the new primary.
4. **Update IaC** to drop `createMode` / `create_mode` and `replicaParameters` for the promoted cluster so subsequent runs don't try to re-link it.
5. **Restore DR coverage.** Step 1 already reconfigures the ex-primary as the new replica when its region is healthy, so you may already have a cross-region pair again — verify in the portal. **A new replica only needs to be established if** the ex-primary's region is permanently unavailable, the ex-primary cluster cannot be recovered, or you want DR coverage in a *different* region than before. In any of those cases, create a new replica (in the original region once it recovers, or in a new DR region) to retain the 99.995% combined SLA.
6. **Reconfigure networking on the promoted cluster** if needed — firewall rules and Private Endpoints are independent per cluster, so the new primary should already have its own; verify the rule set matches what the app expects from a primary.

See [Replica cluster promotion](https://learn.microsoft.com/azure/documentdb/cross-region-replication#replica-cluster-promotion) and [Manage cluster replication — Promote a replica](https://learn.microsoft.com/azure/documentdb/how-to-cluster-replica#promote-a-replica).

### Monitoring the replica

The replica is a full first-class cluster resource and has **its own Metrics** for resource consumption (CPU, memory, IOPS, storage, connections). Replica metrics are **not** aggregated into the primary's metrics — monitor both clusters independently and set alerts on each. See the `documentdb-monitoring` skill for the metric catalog and alerting patterns.

### Authentication, identity, and billing

Authentication and identity are managed differently from networking — note where each lives:

- **Admin account is inherited.** The replica reuses the primary's administrator credentials at creation time. You do not (and cannot) re-supply admin credentials on the replica.
- **Users and managed identities are managed on the primary.** Application user accounts and managed-identity assignments are **always created on the primary** and synchronized to the replica automatically. Connect to either cluster with the same credentials. Do not try to create users on the replica.
- **Authentication *methods* are managed per-cluster.** Native DocumentDB authentication and Microsoft Entra authentication can be toggled independently on the primary and the replica.
- **Native-auth gotcha at replica creation.** If native DocumentDB authentication is **disabled on the primary at the moment the replica is created**, you **cannot enable native auth on the replica later** without first promoting it. If you anticipate ever needing native auth on the replica (e.g. for a tool that doesn't support Entra), turn it on **before** provisioning the replica.
- **Billing.** A replica is a full first-class cluster — you pay for its provisioned vCores and GiB/month of storage on the same pricing structure as a standalone cluster, at the **replica region's** Azure prices. Plan replica region selection with cost in mind (some regions are materially more expensive than others).

### Replica networking, encryption, and lifecycle

These are independent per cluster — set them on the replica too, not just the primary:

- **Networking** (firewall rules / Private Endpoints) is **independent on the replica**. To make the replica reachable for reads, configure its public-network access rules or wire up a Private Endpoint in the replica's region. The primary's networking is **not** inherited.
- **Customer-Managed Keys (CMK)** can be configured on the replica at creation time, including a different CMK than the primary if you want region-local key isolation. CMK on an existing replica follows the same flow as on a standalone cluster.
- **Disabling replication = deleting the replica.** There is no "disable replication" toggle. Delete the replica cluster from the Azure portal (or `az rest` DELETE) and the primary returns to standalone state. Deleting the replica does **not** affect data on or writes to the primary.
- **Deletion order matters.** You **cannot delete the primary while a replica exists.** Delete the replica first, then the primary.
- **Replica subscription / RG.** When created via portal during initial primary provisioning, the replica is placed in the **same subscription and resource group** as the primary. When created via IaC (Bicep / Terraform / REST), the replica may be deployed into a **different resource group** (and even a different region's RG); only `sourceResourceId` and `sourceLocation` matter for linkage.

## References

- [HA & cross-region replication best practices](https://learn.microsoft.com/azure/documentdb/high-availability-replication-best-practices)
- [Reliability in Azure DocumentDB](https://learn.microsoft.com/azure/reliability/reliability-documentdb) — shared-responsibility DR model, manual cross-region promotion
- [Availability and disaster recovery in Azure DocumentDB — behind the scenes](https://learn.microsoft.com/azure/documentdb/availability-disaster-recovery-under-hood) — asynchronous replication mechanics, replication-lag drivers, RPO honesty
- [Cross-region replication](https://learn.microsoft.com/azure/documentdb/cross-region-replication)
- [Manage cluster replication](https://learn.microsoft.com/azure/documentdb/how-to-cluster-replica)
- [Troubleshoot cluster replication](https://learn.microsoft.com/azure/documentdb/troubleshoot-replication) — replica networking gotchas, per-cluster metrics, failback semantics
- [`MongoClusterReplicaParameters` (ARM/Bicep)](https://learn.microsoft.com/azure/templates/microsoft.documentdb/mongoclusters#mongoclusterreplicaparameters)
- [`azurerm_mongo_cluster` — `create_mode`, `source_server_id`, `source_location`](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/mongo_cluster)
