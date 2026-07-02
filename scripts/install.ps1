<#
.SYNOPSIS
  Install the documentdb-agent-kit skills into an agent's skills directory,
  with OPTIONAL, opt-in usage telemetry.

.DESCRIPTION
  Copies (or symlinks) the skills/ folder into a target agent directory.
  Telemetry is OFF by default. It is only sent when you explicitly pass
  -Telemetry, or set the environment variable DDBKIT_TELEMETRY=1.

  When enabled, a single anonymous "install" event is sent to Azure
  Application Insights recording: which target agent was used, the list of
  skill names installed, kit version, and coarse OS family. No file contents,
  no personal data, no connection strings, and no machine identifiers beyond a
  random per-invocation id are collected. See TELEMETRY.md for the full schema.

.PARAMETER Target
  Where to install: 'claude-user', 'claude-project', or a custom path.

.PARAMETER Telemetry
  Opt in to sending the anonymous install event.

.PARAMETER Symlink
  Symlink instead of copy (requires privilege/developer mode on Windows).

.EXAMPLE
  ./scripts/install.ps1 -Target claude-project

.EXAMPLE
  ./scripts/install.ps1 -Target claude-user -Telemetry
#>
[CmdletBinding()]
param(
    [ValidateNotNullOrEmpty()]
    [string]$Target = 'claude-project',
    [switch]$Telemetry,
    [switch]$Symlink
)

$ErrorActionPreference = 'Stop'

# --- Config -----------------------------------------------------------------
$KitVersion = '1.0.0'
# App Insights ingestion key. Supply your own via the DDBKIT_AIKEY environment
# variable. An instrumentation key is an ingestion-only identifier; it is kept
# out of source control here so the repo ships without a live endpoint.
$InstrumentationKey = if ($env:DDBKIT_AIKEY) { $env:DDBKIT_AIKEY } else { '<YOUR_APPINSIGHTS_INSTRUMENTATION_KEY>' }
$IngestionEndpoint  = 'https://dc.services.visualstudio.com/v2/track'

$RepoRoot   = Split-Path -Parent $PSScriptRoot
$SkillsRoot = Join-Path $RepoRoot 'skills'

if (-not (Test-Path $SkillsRoot)) {
    throw "skills/ not found at '$SkillsRoot'. Run this from inside the documentdb-agent-kit repo."
}

# --- Resolve target directory ----------------------------------------------
switch ($Target) {
    'claude-project' { $Dest = Join-Path $RepoRoot '.claude/skills' }
    'claude-user'    { $Dest = Join-Path $HOME '.claude/skills' }
    default          { $Dest = $Target }
}

New-Item -ItemType Directory -Force -Path $Dest | Out-Null

# --- Install ----------------------------------------------------------------
$installed = @()
Get-ChildItem -Path $SkillsRoot -Directory | ForEach-Object {
    $name = $_.Name
    $linkPath = Join-Path $Dest $name
    if (Test-Path $linkPath) { Remove-Item $linkPath -Recurse -Force }

    if ($Symlink) {
        New-Item -ItemType SymbolicLink -Path $linkPath -Target $_.FullName | Out-Null
    }
    else {
        Copy-Item -Path $_.FullName -Destination $linkPath -Recurse -Force
    }
    $installed += $name
}

Write-Host "Installed $($installed.Count) skills into $Dest" -ForegroundColor Green
$installed | ForEach-Object { Write-Host "  - $_" }

# --- Opt-in telemetry -------------------------------------------------------
$telemetryOn = $Telemetry -or ($env:DDBKIT_TELEMETRY -eq '1')

if (-not $telemetryOn) {
    Write-Host ''
    Write-Host 'Usage telemetry: OFF. Re-run with -Telemetry (or set DDBKIT_TELEMETRY=1) to' -ForegroundColor DarkGray
    Write-Host 'help the maintainers see which skills are installed. See TELEMETRY.md.'    -ForegroundColor DarkGray
    return
}

if ($InstrumentationKey -like '<*>') {
    Write-Host ''
    Write-Host 'Telemetry requested but no App Insights key configured. Set DDBKIT_AIKEY to enable. Skipping.' -ForegroundColor DarkYellow
    return
}

try {
    $osFamily = if ($IsWindows) { 'windows' } elseif ($IsMacOS) { 'macos' } elseif ($IsLinux) { 'linux' } else { 'unknown' }

    $payload = @{
        name = 'Microsoft.ApplicationInsights.Event'
        time = (Get-Date).ToUniversalTime().ToString('o')
        iKey = $InstrumentationKey
        tags = @{ 'ai.cloud.role' = 'documentdb-agent-kit-installer' }
        data = @{
            baseType = 'EventData'
            baseData = @{
                ver        = 2
                name       = 'skill_install'
                properties = @{
                    kitVersion  = $KitVersion
                    target      = $Target
                    osFamily    = $osFamily
                    method      = if ($Symlink) { 'symlink' } else { 'copy' }
                    skills      = ($installed -join ',')
                    invocationId = [guid]::NewGuid().ToString()
                }
                measurements = @{ skillCount = $installed.Count }
            }
        }
    } | ConvertTo-Json -Depth 6 -Compress

    Invoke-RestMethod -Uri $IngestionEndpoint -Method Post -Body $payload -ContentType 'application/json' -TimeoutSec 10 | Out-Null
    Write-Host ''
    Write-Host 'Anonymous install event sent. Thank you!' -ForegroundColor Green
}
catch {
    # Telemetry must never break an install.
    Write-Host ''
    Write-Host "Telemetry send failed (ignored): $($_.Exception.Message)" -ForegroundColor DarkYellow
}
