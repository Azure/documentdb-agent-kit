# Bicep cluster template — Azure DocumentDB

Canonical template for `Microsoft.DocumentDB/mongoClusters` (API version `2025-09-01`), adapted from the official [Azure DocumentDB Bicep quickstart](https://learn.microsoft.com/azure/documentdb/quickstart-bicep).

## `main.bicep` (dev-tier, public + "Allow Azure services")

```bicep
@description('Cluster name (globally unique; 8–40 chars; lowercase letters / digits / hyphens).')
@minLength(8)
@maxLength(40)
param clusterName string = 'docdb-${uniqueString(resourceGroup().id)}'

@description('Azure region for the cluster.')
param location string = resourceGroup().location

@description('Administrator username for the cluster.')
param adminUsername string

@secure()
@description('Administrator password (8–128 chars). Source from Key Vault — never commit.')
@minLength(8)
@maxLength(128)
param adminPassword string

@description('Compute tier: M10 (dev), M20, M30 (min for HA), M40, M50, M60, M80, M200.')
@allowed([
  'M10'
  'M20'
  'M30'
  'M40'
  'M50'
  'M60'
  'M80'
  'M200'
])
param computeTier string = 'M30'

@description('Storage per shard, in GiB.')
@minValue(32)
param storageSizeGb int = 128

@description('Shard count. Start at 1; sufficient until TB scale.')
@minValue(1)
param shardCount int = 1

@description('High availability mode. Requires M30+ for non-Disabled values.')
@allowed([
  'Disabled'
  'SameZone'
  'ZoneRedundantPreferred'
])
param haTargetMode string = 'ZoneRedundantPreferred'

@description('MongoDB wire-protocol server version.')
param serverVersion string = '8.0'

resource cluster 'Microsoft.DocumentDB/mongoClusters@2025-09-01' = {
  name: clusterName
  location: location
  properties: {
    administrator: {
      userName: adminUsername
      password: adminPassword
    }
    serverVersion: serverVersion
    sharding: {
      shardCount: shardCount
    }
    storage: {
      sizeGb: storageSizeGb
    }
    highAvailability: {
      targetMode: haTargetMode
    }
    compute: {
      tier: computeTier
    }
  }
}

// "Allow Azure services and resources within Azure to access this cluster."
// This is the documented shortcut: start and end both 0.0.0.0.
// For prod with Private Endpoint, remove this rule and set publicNetworkAccess: 'Disabled'.
resource allowAzureServices 'Microsoft.DocumentDB/mongoClusters/firewallRules@2025-09-01' = {
  parent: cluster
  name: 'AllowAllAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

@description('Fully qualified connection string (password is the placeholder <password>).')
output connectionString string = cluster.properties.connectionString

@description('Cluster resource ID — useful for Private Endpoint / Entra RBAC assignments.')
output clusterId string = cluster.id
```

## `main.parameters.json`

```json
{
  "$schema": "https://schema.management.azure.com/schemas/2015-01-01/deploymentParameters.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "clusterName":    { "value": "docdb-prod-001" },
    "adminUsername":  { "value": "clusteradmin" },
    "adminPassword":  {
      "reference": {
        "keyVault": { "id": "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.KeyVault/vaults/<kv-name>" },
        "secretName": "docdb-admin-password"
      }
    },
    "computeTier":    { "value": "M30" },
    "storageSizeGb":  { "value": 128 },
    "haTargetMode":   { "value": "ZoneRedundantPreferred" }
  }
}
```

**Never** substitute `adminPassword` with a literal string in a committed file. Use Key Vault references, or pass `--parameters adminPassword="..."` inline from a secure source.

## Prod variant — Private Endpoint

Add to the template (requires an existing VNet + subnet with `privateEndpointNetworkPolicies: Disabled`):

```bicep
@description('Resource ID of the subnet that hosts the Private Endpoint.')
param privateEndpointSubnetId string

// Disable public access on the cluster (replace the firewall rule above)
resource cluster 'Microsoft.DocumentDB/mongoClusters@2025-09-01' = {
  name: clusterName
  location: location
  properties: {
    // ...same as before...
    publicNetworkAccess: 'Disabled'
  }
}

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: '${clusterName}-pe'
  location: location
  properties: {
    subnet: { id: privateEndpointSubnetId }
    privateLinkServiceConnections: [
      {
        name: '${clusterName}-plsc'
        properties: {
          privateLinkServiceId: cluster.id
          groupIds: [ 'MongoCluster' ]
        }
      }
    ]
  }
}
```

After deploy, attach the Private DNS zone `privatelink.mongocluster.cosmos.azure.com` to the VNet and create the A record for the Private Endpoint — see `documentdb-security` for the full pattern.

## Deploy

```bash
az group create --name "<rg>" --location "<location>"

az deployment group create \
  --resource-group "<rg>" \
  --template-file main.bicep \
  --parameters @main.parameters.json
```

Outputs include the connection string (with `<password>` placeholder) and cluster resource ID. Never log the connection string — it contains the admin username.

## References

- [Bicep quickstart](https://learn.microsoft.com/azure/documentdb/quickstart-bicep)
- [`Microsoft.DocumentDB/mongoClusters` resource reference](https://learn.microsoft.com/azure/templates/microsoft.documentdb/mongoclusters)
- [Key Vault secret reference in parameters file](https://learn.microsoft.com/azure/azure-resource-manager/templates/key-vault-parameter)
