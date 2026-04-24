# ha-cross-region-replica

**Category:** High Availability & Replication · **Priority:** MEDIUM

## Why it matters

Azure DocumentDB supports **active-passive cross-region replication**: one cluster is the read-write primary, a replica cluster in another region stays read-only and in sync. If a region fails, the replica can be promoted to take writes with minimal interruption. Combined with in-region HA, this delivers the **99.995% SLA** and enables:
- Disaster recovery across regions.
- Read-scale offload to the replica for heavy analytical reads.

## Incorrect

Relying solely on in-region HA for a mission-critical global application:

```text
Single-region cluster, HA: on
- Survives node failure (good)
- Does NOT survive regional outage
- No read-scale offload for distant users
```

## Correct

Pair HA + cross-region replica for production-critical workloads:

1. Enable HA on the primary cluster (see `ha-enable-for-production`).
2. Create a replica cluster (`createMode: 'GeoReplica'`) in a paired or geographically near region. The replica reuses the primary's admin credentials, databases, collections, and documents — only the cluster name and region differ.
3. Route latency-sensitive reads in that region to the replica's connection string (read-only).
4. Document a tested promotion runbook for DR; validate periodically.

```text
Primary:   East US 2  (read-write, HA on)
Replica:   West US 3  (read-only,  HA on)
Combined SLA: 99.995%
```

Design for eventual consistency on the replica; writes must still target the primary until you explicitly promote the replica.

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

The replica may be deployed into a **different resource group** (and even a different region's RG) than the primary; only `sourceResourceId` and `sourceLocation` matter for linkage.

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

### Promotion (DR failover)

Promotion is a control-plane action (REST / portal); there is no IaC primitive for it. After promotion, the former replica becomes a standalone read-write cluster — update the IaC to drop `createMode` / `create_mode` and `replicaParameters` so subsequent runs don't try to re-link it. See [Replica cluster promotion](https://learn.microsoft.com/azure/documentdb/cross-region-replication#replica-cluster-promotion).

## References

- [HA & cross-region replication best practices](https://learn.microsoft.com/azure/documentdb/high-availability-replication-best-practices)
- [Cross-region replication](https://learn.microsoft.com/azure/documentdb/cross-region-replication)
- [Manage cluster replication](https://learn.microsoft.com/azure/documentdb/how-to-cluster-replica)
- [`MongoClusterReplicaParameters` (ARM/Bicep)](https://learn.microsoft.com/azure/templates/microsoft.documentdb/mongoclusters#mongoclusterreplicaparameters)
- [`azurerm_mongo_cluster` — `create_mode`, `source_server_id`, `source_location`](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/mongo_cluster)
