<#
.SYNOPSIS
  Deploy an Azure DocumentDB cluster from main.bicep with preflight checks
  and interactive subscription / resource-group / location pickers.

.EXAMPLE
  ./deploy.ps1
  ./deploy.ps1 -ResourceGroup rg-docdb-dev -Location eastus2 -ParametersFile main.parameters.dev.json
#>
[CmdletBinding()]
param(
    [string] $ResourceGroup,
    [string] $Location,
    [string] $ParametersFile,
    [switch] $SkipConfirm
)

$ErrorActionPreference = 'Stop'

function Write-Info { param($m) Write-Host "[info]  $m" -ForegroundColor Cyan }
function Write-Ok   { param($m) Write-Host "[ok]    $m" -ForegroundColor Green }
function Write-Warn2{ param($m) Write-Host "[warn]  $m" -ForegroundColor Yellow }
function Die        { param($m) Write-Host "[error] $m" -ForegroundColor Red; exit 1 }

function Invoke-Pick {
    param(
        [Parameter(Mandatory = $true)] [string[]] $Items,
        [Parameter(Mandatory = $true)] [string]   $Prompt
    )
    if ($Items.Count -eq 0) { Die "Nothing to pick from." }
    Write-Host ""
    for ($i = 0; $i -lt $Items.Count; $i++) {
        Write-Host ("  {0,2}) {1}" -f ($i + 1), $Items[$i])
    }
    while ($true) {
        $choice = Read-Host "`n$Prompt [1-$($Items.Count)]"
        if ($choice -match '^\d+$') {
            $n = [int]$choice
            if ($n -ge 1 -and $n -le $Items.Count) { return $Items[$n - 1] }
        }
        Write-Warn2 "Invalid choice."
    }
}

# ---------------------------------------------------------------------------
# Step 0 — preflight checks
# ---------------------------------------------------------------------------
Write-Info "Preflight checks..."

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    Die "Azure CLI ('az') not found. Install: https://learn.microsoft.com/cli/azure/install-azure-cli"
}
Write-Ok "Azure CLI found: $(az version --query '\"azure-cli\"' -o tsv)"

az account show 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warn2 "Not signed in to Azure. Launching 'az login'..."
    az login | Out-Null
}

# ---------------------------------------------------------------------------
# Step 1 — pick subscription
# ---------------------------------------------------------------------------
$subsJson = az account list --query "[?state=='Enabled'].{name:name, id:id}" -o json | ConvertFrom-Json
if (-not $subsJson -or $subsJson.Count -eq 0) { Die "No enabled subscriptions found for this account." }

if ($subsJson.Count -eq 1) {
    $chosenSub = $subsJson[0]
    Write-Info "Only one subscription available: $($chosenSub.name)"
} else {
    Write-Info "Available subscriptions:"
    $display = $subsJson | ForEach-Object { "$($_.name) | $($_.id)" }
    $choice  = Invoke-Pick -Items $display -Prompt "Pick a subscription"
    $chosenSub = $subsJson | Where-Object { "$($_.name) | $($_.id)" -eq $choice } | Select-Object -First 1
}
az account set --subscription $chosenSub.id
Write-Ok "Using subscription: $($chosenSub.name) ($($chosenSub.id))"

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

# ---------------------------------------------------------------------------
# Step 2 — pick (or create) resource group
# ---------------------------------------------------------------------------
if (-not $ResourceGroup) {
    $existing = az group list --query "[].{name:name, location:location}" -o json | ConvertFrom-Json
    $menu = @()
    if ($existing -and $existing.Count -gt 0) {
        $menu += ($existing | ForEach-Object { "$($_.name) | $($_.location)" })
    }
    $menu += "<create new resource group>"
    Write-Info "Resource groups in '$($chosenSub.name)':"
    $rgChoice = Invoke-Pick -Items $menu -Prompt "Pick a resource group"
    if ($rgChoice -eq "<create new resource group>") {
        $ResourceGroup = Read-Host "New resource group name"
        if (-not $ResourceGroup) { Die "Resource group name required." }
    } else {
        $ResourceGroup = ($rgChoice -split ' \| ')[0]
        $locFromRg     = ($rgChoice -split ' \| ')[1]
        if (-not $Location) { $Location = $locFromRg }
        Write-Info "Using existing resource group '$ResourceGroup' in '$locFromRg'"
    }
}

# ---------------------------------------------------------------------------
# Step 3 — pick location (only needed when the RG doesn't exist yet)
# ---------------------------------------------------------------------------
az group show --name $ResourceGroup 2>$null | Out-Null
$rgExists = ($LASTEXITCODE -eq 0)

if (-not $rgExists) {
    if (-not $Location) {
        Write-Info "Regions that support Microsoft.DocumentDB/mongoClusters:"
        $locs = az provider show --namespace Microsoft.DocumentDB `
            --query "resourceTypes[?resourceType=='mongoClusters'].locations[]" -o tsv
        $locArr = ($locs -split "`n") | Where-Object { $_ } | Sort-Object -Unique
        if ($locArr.Count -eq 0) { Die "Could not fetch supported regions." }
        $Location = Invoke-Pick -Items $locArr -Prompt "Pick a region"
    }
    Write-Info "Creating resource group '$ResourceGroup' in '$Location'..."
    az group create --name $ResourceGroup --location $Location | Out-Null
    Write-Ok "Created resource group: $ResourceGroup"
} else {
    if (-not $Location) { $Location = az group show --name $ResourceGroup --query location -o tsv }
    Write-Ok "Resource group exists: $ResourceGroup (location: $Location)"
}

# ---------------------------------------------------------------------------
# Step 4 — summarise intended deployment and confirm
# ---------------------------------------------------------------------------
if ($ParametersFile) {
    if (-not (Test-Path $ParametersFile)) { Die "Parameters file not found: $ParametersFile" }
    Write-Info "Parameters file: $ParametersFile"
} else {
    Write-Warn2 "No parameters file provided — main.bicep defaults will apply:"
    Write-Warn2 "    computeTier   = M30           (production-class; not free tier)"
    Write-Warn2 "    storageSizeGb = 128 GiB"
    Write-Warn2 "    haTargetMode  = ZoneRedundantPreferred (requires M30+)"
    Write-Warn2 "    shardCount    = 1"
    Write-Warn2 "For dev/test, re-run with: -ParametersFile main.parameters.dev.json"
}

if (-not $SkipConfirm) {
    $reply = Read-Host "Proceed with deployment to '$ResourceGroup' in '$Location'? [y/N]"
    if ($reply -notmatch '^(y|Y|yes|YES)$') { Die "Aborted by user." }
}

# ---------------------------------------------------------------------------
# Step 5 — deploy
# ---------------------------------------------------------------------------
$bicepPath = Join-Path $PSScriptRoot 'main.bicep'
$deployArgs = @('deployment', 'group', 'create',
                '--resource-group', $ResourceGroup,
                '--template-file', $bicepPath)

if ($ParametersFile) {
    $deployArgs += @('--parameters', "@$ParametersFile")
} else {
    Write-Info "You'll be prompted for adminUsername and adminPassword."
}

Write-Info "Deploying cluster (this typically takes 8–12 minutes)..."
az @deployArgs --query "properties.outputs" --output json

Write-Ok "Deployment complete. Retrieve the connection string from: Azure portal -> cluster -> Connection strings"
