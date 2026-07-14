// Deploys the telemetry relay: Log Analytics workspace, Application Insights,
// a consumption-plan Function App (Linux/Node), and its storage account.
// The App Insights connection string is wired into the Function's app settings
// automatically — it is never emitted to the repo or the client.
//
// Deploy:
//   az group create -n <rg> -l <location>
//   az deployment group create -g <rg> -f main.bicep -p namePrefix=<prefix>

@description('Short prefix for resource names (3-11 lowercase alphanumeric).')
@minLength(3)
@maxLength(11)
param namePrefix string

@description('Azure region for all resources.')
param location string = resourceGroup().location

var suffix = uniqueString(resourceGroup().id)
var storageName = toLower('${namePrefix}st${substring(suffix, 0, 6)}')
var planName = '${namePrefix}-plan'
var funcName = '${namePrefix}-func-${substring(suffix, 0, 6)}'
var lawName = '${namePrefix}-law'
var aiName = '${namePrefix}-ai'

resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: lawName
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 90
  }
}

resource ai 'Microsoft.Insights/components@2020-02-02' = {
  name: aiName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: law.id
    IngestionMode: 'LogAnalytics'
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: planName
  location: location
  sku: { name: 'Y1', tier: 'Dynamic' }
  properties: { reserved: true }
}

resource func 'Microsoft.Web/sites@2023-12-01' = {
  name: funcName
  location: location
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'Node|20'
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      cors: {
        allowedOrigins: ['*']
      }
      appSettings: [
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'node' }
        { name: 'WEBSITE_NODE_DEFAULT_VERSION', value: '~20' }
        {
          name: 'AzureWebJobsStorage'
          value: 'DefaultEndpointsProtocol=https;AccountName=${storage.name};EndpointSuffix=${environment().suffixes.storage};AccountKey=${storage.listKeys().keys[0].value}'
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: ai.properties.ConnectionString
        }
      ]
    }
  }
}

@description('POST install events to this URL from the installers.')
output collectUrl string = 'https://${func.properties.defaultHostName}/api/collect'

@description('Application Insights resource name (for the Grafana Azure Monitor data source).')
output appInsightsName string = ai.name

@description('Log Analytics workspace name (query custom events here / in Grafana).')
output logAnalyticsWorkspace string = law.name
