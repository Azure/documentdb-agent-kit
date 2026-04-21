<#
.SYNOPSIS
  Deploy an Azure DocumentDB cluster from main.bicep with preflight checks.

.EXAMPLE
  ./deploy.ps1 -ResourceGroup rg-docdb-dev -Location eastus2 -ParametersFile main.parameters.sample.json
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $ResourceGroup,
    [Parameter(Mandatory = $true)] [string] $Location,
    [string] $ParametersFile
)

$ErrorActionPreference = 'Stop'

function Write-Info { param($m) Write-Host "[info]  $m" -ForegroundColor Cyan }
function Write-Ok   { param($m) Write-Host "[ok]    $m" -ForegroundColor Green }
function Write-Warn2{ param($m) Write-Host "[warn]  $m" -ForegroundColor Yellow }
function Die        { param($m) Write-Host "[error] $m" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------------------
# Step 0 — preflight checks
# ---------------------------------------------------------------------------
Write-Info "Preflight checks..."

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    Die "Azure CLI ('az') not found. Install: https://learn.microsoft.com/cli/azure/install-azure-cli"
}
$azVersion = (az version --query '"azure-cli"' -o tsv)
Write-Ok "Azure CLI found: $azVersion"

try { az account show 2>$null | Out-Null } catch { }
if ($LASTEXITCODE -ne 0) {
    Write-Warn2 "Not signed in to Azure. Launching 'az login'..."
    az login | Out-Null
}
$subName = az account show --query name -o tsv
$subId   = az account show --query id   -o tsv
Write-Ok "Signed in to subscription: $subName ($subId)"

$regState = az provider show --namespace Microsoft.DocumentDB --query registrationState -o tsv 2>$null
if (-not $regState) { $regState = 'NotRegistered' }
if ($regState -ne 'Registered') {
    Write-Warn2 "Microsoft.DocumentDB provider is '$regState' — registering..."
    az provider register --namespace Microsoft.DocumentDB | Out-Null
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 5
        $regState = az provider show --namespace Microsoft.DocumentDB --query registrationState -o tsv
        if ($regState -eq 'Registered') { break }
    }
    if ($regState -ne 'Registered') { Die "Provider registration timed out (state: $regState)" }
}
Write-Ok "Microsoft.DocumentDB provider: Registered"

az group show --name $ResourceGroup 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Info "Resource group '$ResourceGroup' does not exist — creating in $Location..."
    az group create --name $ResourceGroup --location $Location | Out-Null
    Write-Ok "Created resource group: $ResourceGroup"
} else {
    Write-Ok "Resource group exists: $ResourceGroup"
}

# ---------------------------------------------------------------------------
# Step 1 — deploy
# ---------------------------------------------------------------------------
$bicepPath = Join-Path $PSScriptRoot 'main.bicep'
$deployArgs = @('deployment', 'group', 'create',
                '--resource-group', $ResourceGroup,
                '--template-file', $bicepPath)

if ($ParametersFile) {
    if (-not (Test-Path $ParametersFile)) { Die "Parameters file not found: $ParametersFile" }
    $deployArgs += @('--parameters', "@$ParametersFile")
    Write-Info "Deploying with parameters file: $ParametersFile"
} else {
    Write-Info "No parameters file provided — you'll be prompted for adminUsername and adminPassword."
}

Write-Info "Deploying cluster (this typically takes 8–12 minutes)..."
az @deployArgs --query "properties.outputs" --output json

Write-Ok "Deployment complete. Retrieve the connection string from: Azure portal -> cluster -> Connection strings"
