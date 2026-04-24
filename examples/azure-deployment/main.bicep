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

@description('Compute tier. Defaults to M30 which is the minimum for HA. Use M10/M20 only for dev/test.')
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

@description('High availability mode. ZoneRedundantPreferred is production-safe and requires M30+. Set to Disabled for dev/test to reduce cost.')
@allowed([
  'Disabled'
  'SameZone'
  'ZoneRedundantPreferred'
])
param haTargetMode string = 'ZoneRedundantPreferred'

@description('MongoDB wire-protocol server version.')
param serverVersion string = '8.0'

@description('Whether to create the "Allow Azure services" firewall rule (0.0.0.0-0.0.0.0 shortcut). Set false for Private Endpoint deployments.')
param allowAzureServices bool = true

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

resource allowAzureServicesRule 'Microsoft.DocumentDB/mongoClusters/firewallRules@2025-09-01' = if (allowAzureServices) {
  parent: cluster
  name: 'AllowAllAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

@description('Cluster resource ID.')
output clusterId string = cluster.id

@description('Cluster name.')
output clusterName string = cluster.name
