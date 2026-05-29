#requires -Version 5.1
<#
.SYNOPSIS
    documentdb-agent-kit installer (Windows + cross-platform PowerShell).

.DESCRIPTION
    Installs DocumentDB skills + the microsoft/documentdb-mcp server into every
    detected MCP client (Claude Code, Claude Desktop, Cursor, Copilot CLI,
    Gemini CLI).

.PARAMETER Uri
    DocumentDB / MongoDB connection string. If omitted, the script checks
    $env:DOCUMENTDB_URI, then prompts interactively.

.PARAMETER Yes
    Non-interactive; never prompt.

.PARAMETER DryRun
    Print planned changes; write nothing.

.PARAMETER Uninstall
    Remove the kit's MCP entries + skill symlinks, then remove ~/.documentdb-agent-kit.

.PARAMETER Clients
    Comma-separated subset of: claude-code,claude-desktop,cursor,copilot-cli,gemini-cli

.PARAMETER SkillsOnly
    Install skills only; skip the MCP server.

.PARAMETER McpOnly
    Install the MCP server only; skip skills.

.PARAMETER McpRef
    Git ref of microsoft/documentdb-mcp to build (default: main).

.PARAMETER KitRef
    Git ref of Azure/documentdb-agent-kit to install (default: main).

.PARAMETER Profile
    Name to use in CONNECTION_PROFILES (default: default).

.EXAMPLE
    irm https://raw.githubusercontent.com/Azure/documentdb-agent-kit/main/install.ps1 | iex

.EXAMPLE
    .\install.ps1 -Uri "mongodb://localhost:27017" -Yes

.EXAMPLE
    .\install.ps1 -Uninstall
#>

[CmdletBinding()]
param(
    [string]$Uri = "",
    [switch]$Yes,
    [switch]$DryRun,
    [switch]$Uninstall,
    [string]$Clients = "",
    [switch]$SkillsOnly,
    [switch]$McpOnly,
    [string]$McpRef = "main",
    [string]$KitRef = "main",
    [string]$Profile = "default"
)

$ErrorActionPreference = "Stop"

# ---------- Constants ----------
$KIT_REPO     = "https://github.com/Azure/documentdb-agent-kit.git"
$MCP_REPO     = "https://github.com/microsoft/documentdb-mcp.git"
$INSTALL_ROOT = Join-Path $HOME ".documentdb-agent-kit"
$KIT_DIR      = Join-Path $INSTALL_ROOT "agent-kit"
$MCP_DIR      = Join-Path $INSTALL_ROOT "mcp-server"
$MCP_ENTRY    = "DocumentDB"
$MIN_NODE_MAJOR = 20
$SUPPORTED_CLIENTS = @("claude-code","claude-desktop","cursor","copilot-cli","gemini-cli")

# ---------- OS detection ----------
$IsWin = $false
$IsMac = $false
$IsLin = $false
if ($PSVersionTable.PSVersion.Major -ge 6) {
    $IsWin = $IsWindows
    $IsMac = $IsMacOS
    $IsLin = $IsLinux
} else {
    $IsWin = $true   # Windows PowerShell 5.1
}

# ---------- Logging ----------
$useColor = $Host.UI.RawUI -ne $null -and -not $env:NO_COLOR
function Write-Info([string]$msg)    { Write-Host "→ $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg)      { Write-Host "✓ $msg" -ForegroundColor Green }
function Write-Warn2([string]$msg)   { Write-Host "! $msg" -ForegroundColor Yellow }
function Write-Err([string]$msg)     { Write-Host "✗ $msg" -ForegroundColor Red }
function Write-Heading([string]$msg) { Write-Host ""; Write-Host $msg -ForegroundColor White -BackgroundColor Black }
function Write-Dry([string]$msg)     { if ($DryRun) { Write-Host "[dry-run] $msg" -ForegroundColor DarkGray } }

# ---------- Client config paths ----------
function Get-ClientMcpConfigPath([string]$client) {
    switch ($client) {
        "claude-code"    { return (Join-Path $HOME ".claude.json") }
        "claude-desktop" {
            if ($IsWin) {
                return (Join-Path $env:APPDATA "Claude\claude_desktop_config.json")
            } elseif ($IsMac) {
                return (Join-Path $HOME "Library/Application Support/Claude/claude_desktop_config.json")
            } else {
                return (Join-Path $HOME ".config/Claude/claude_desktop_config.json")
            }
        }
        "cursor"         { return (Join-Path $HOME ".cursor/mcp.json") }
        "copilot-cli"    { return (Join-Path $HOME ".copilot/mcp-config.json") }
        "gemini-cli"     { return (Join-Path $HOME ".gemini/settings.json") }
        default          { throw "unknown client: $client" }
    }
}

function Get-ClientSkillsDir([string]$client) {
    switch ($client) {
        "claude-code"    { return (Join-Path $HOME ".claude/skills") }
        "claude-desktop" {
            if ($IsWin) {
                return (Join-Path $env:APPDATA "Claude\skills")
            } elseif ($IsMac) {
                return (Join-Path $HOME "Library/Application Support/Claude/skills")
            } else {
                return (Join-Path $HOME ".config/Claude/skills")
            }
        }
        default          { return $null }
    }
}

function Get-ClientLabel([string]$client) {
    switch ($client) {
        "claude-code"    { return "Claude Code" }
        "claude-desktop" { return "Claude Desktop" }
        "cursor"         { return "Cursor" }
        "copilot-cli"    { return "GitHub Copilot CLI" }
        "gemini-cli"     { return "Gemini CLI" }
        default          { return $client }
    }
}

function Test-McpOnlyClient([string]$client) {
    return $client -in @("cursor","copilot-cli","gemini-cli")
}

# ---------- Detection ----------
function Find-InstalledClients {
    $found = @()
    foreach ($c in $SUPPORTED_CLIENTS) {
        $cfg = Get-ClientMcpConfigPath $c
        $parent = Split-Path $cfg -Parent
        if ((Test-Path $cfg) -or (Test-Path $parent)) {
            $found += $c
        }
    }
    return $found
}

function Filter-ClientsByUser([string[]]$detected) {
    if ([string]::IsNullOrWhiteSpace($Clients)) { return $detected }
    $allow = $Clients -split ","
    return $detected | Where-Object { $_ -in $allow }
}

# ---------- Prereqs ----------
function Test-Command([string]$name) {
    $null -ne (Get-Command $name -ErrorAction SilentlyContinue)
}

function Test-Prereqs {
    $missing = $false
    if (-not (Test-Command "git")) {
        Write-Err "git is required"; $missing = $true
    }
    if ($McpOnly -or -not $SkillsOnly) {
        if (-not (Test-Command "node")) {
            Write-Err "node is required (Node.js ${MIN_NODE_MAJOR}+ for the MCP server)"; $missing = $true
        } else {
            $nodeVer = (& node --version) -replace '^v',''
            $major = [int]($nodeVer -split '\.')[0]
            if ($major -lt $MIN_NODE_MAJOR) {
                Write-Err "Node.js ${MIN_NODE_MAJOR}+ required, found v$nodeVer"; $missing = $true
            }
        }
        if (-not (Test-Command "npm")) {
            Write-Err "npm is required (ships with Node.js)"; $missing = $true
        }
    }
    if ($missing) { exit 1 }
}

# ---------- JSON merge ----------
function Merge-McpEntry {
    param(
        [string]$ConfigPath,
        [string]$TopKey,
        [string]$ServerCommand,
        [string[]]$ServerArgs,
        [hashtable]$EnvVars
    )

    if ($DryRun) {
        Write-Dry "would merge $MCP_ENTRY entry into $ConfigPath under $TopKey"
        return
    }

    $parent = Split-Path $ConfigPath -Parent
    if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }

    $cfg = [ordered]@{}
    if (Test-Path $ConfigPath) {
        $bak = "$ConfigPath.bak.$(Get-Date -Format 'yyyyMMddHHmmss')"
        Copy-Item -Path $ConfigPath -Destination $bak -Force
        Write-Info "backed up existing config → $bak"
        try {
            $raw = Get-Content -Raw -Path $ConfigPath
            if (-not [string]::IsNullOrWhiteSpace($raw)) {
                # ConvertFrom-Json returns PSCustomObject; turn into ordered hashtable for safe mutation
                $cfg = ConvertTo-OrderedHashtable (ConvertFrom-Json $raw)
            }
        } catch {
            Write-Warn2 "existing $ConfigPath was not valid JSON; replacing it"
            $cfg = [ordered]@{}
        }
    }

    # Navigate / create nested keys (supports dotted top-level like "mcp.servers")
    $parts = $TopKey -split '\.'
    $node = $cfg
    for ($i = 0; $i -lt $parts.Length; $i++) {
        $p = $parts[$i]
        $isLast = ($i -eq $parts.Length - 1)
        if ($isLast) {
            if (-not $node.Contains($p) -or -not ($node[$p] -is [System.Collections.IDictionary])) {
                $node[$p] = [ordered]@{}
            }
            $entry = [ordered]@{
                command = $ServerCommand
                args    = $ServerArgs
                env     = $EnvVars
            }
            $node[$p][$MCP_ENTRY] = $entry
        } else {
            if (-not $node.Contains($p) -or -not ($node[$p] -is [System.Collections.IDictionary])) {
                $node[$p] = [ordered]@{}
            }
            $node = $node[$p]
        }
    }

    $json = $cfg | ConvertTo-Json -Depth 100
    $tmp  = "$ConfigPath.tmp.$([guid]::NewGuid().ToString('N'))"
    Set-Content -Path $tmp -Value $json -Encoding UTF8
    Move-Item -Path $tmp -Destination $ConfigPath -Force
}

function Remove-McpEntry {
    param([string]$ConfigPath, [string]$TopKey)
    if (-not (Test-Path $ConfigPath)) { return }
    if ($DryRun) { Write-Dry "would remove $MCP_ENTRY entry from $ConfigPath"; return }

    $bak = "$ConfigPath.bak.$(Get-Date -Format 'yyyyMMddHHmmss')"
    Copy-Item -Path $ConfigPath -Destination $bak -Force

    try {
        $cfg = ConvertTo-OrderedHashtable (ConvertFrom-Json (Get-Content -Raw -Path $ConfigPath))
    } catch { return }

    $parts = $TopKey -split '\.'
    $node = $cfg
    for ($i = 0; $i -lt $parts.Length; $i++) {
        $p = $parts[$i]
        if (-not $node.Contains($p) -or -not ($node[$p] -is [System.Collections.IDictionary])) { return }
        if ($i -eq $parts.Length - 1) {
            if ($node[$p].Contains($MCP_ENTRY)) { $node[$p].Remove($MCP_ENTRY) }
        } else {
            $node = $node[$p]
        }
    }

    $json = $cfg | ConvertTo-Json -Depth 100
    $tmp  = "$ConfigPath.tmp.$([guid]::NewGuid().ToString('N'))"
    Set-Content -Path $tmp -Value $json -Encoding UTF8
    Move-Item -Path $tmp -Destination $ConfigPath -Force
}

# Helper: deep-convert PSCustomObject → OrderedDictionary so we can mutate it.
function ConvertTo-OrderedHashtable {
    param([Parameter(Mandatory=$false)]$InputObject)
    if ($null -eq $InputObject) { return [ordered]@{} }
    if ($InputObject -is [System.Collections.IDictionary]) {
        $out = [ordered]@{}
        foreach ($k in $InputObject.Keys) { $out[$k] = ConvertTo-OrderedHashtable $InputObject[$k] }
        return $out
    }
    if ($InputObject -is [System.Management.Automation.PSCustomObject]) {
        $out = [ordered]@{}
        foreach ($p in $InputObject.PSObject.Properties) { $out[$p.Name] = ConvertTo-OrderedHashtable $p.Value }
        return $out
    }
    if ($InputObject -is [System.Collections.IList] -and $InputObject -isnot [string]) {
        $list = New-Object System.Collections.ArrayList
        foreach ($item in $InputObject) { [void]$list.Add((ConvertTo-OrderedHashtable $item)) }
        # Return as a proper [object[]] so ConvertTo-Json keeps it as an array
        # even when there is exactly one element.
        return ,@($list.ToArray())
    }
    return $InputObject
}

# ---------- Repos ----------
function Sync-Repo([string]$Repo, [string]$Dest, [string]$Ref) {
    if (Test-Path (Join-Path $Dest ".git")) {
        Write-Info "updating $(Split-Path $Dest -Leaf) (ref: $Ref)"
        if ($DryRun) { Write-Dry "git fetch + checkout $Ref in $Dest"; return }
        Push-Location $Dest
        try {
            git fetch --quiet --tags --depth=1 origin $Ref 2>$null | Out-Null
            git checkout --quiet $Ref 2>$null | Out-Null
            git reset --quiet --hard "FETCH_HEAD" 2>$null | Out-Null
        } finally { Pop-Location }
    } else {
        Write-Info "cloning $Repo → $Dest (ref: $Ref)"
        if ($DryRun) { Write-Dry "git clone --branch $Ref $Repo $Dest"; return }
        & git clone --quiet --depth=1 --branch $Ref $Repo $Dest 2>$null
        if ($LASTEXITCODE -ne 0) {
            & git clone --quiet $Repo $Dest
            Push-Location $Dest
            try { git checkout --quiet $Ref 2>$null | Out-Null } finally { Pop-Location }
        }
    }
}

function Invoke-Npm {
    param([string[]]$NpmArgs)
    if ($IsWin) {
        # On Windows, npm is npm.cmd (a batch shim). PowerShell's `&` call
        # operator can mangle arguments when piping them into .cmd files
        # (notably under PSNativeCommandArgumentPassing defaults on pwsh 7.3+),
        # which manifests as e.g. `Unknown command: "pm"` because the first
        # char of "install" is eaten. Route through cmd.exe to bypass entirely.
        $line = "npm " + ($NpmArgs -join ' ')
        cmd /c $line
    } else {
        & npm @NpmArgs
    }
}

function Build-McpServer {
    if ($DryRun) { Write-Dry "(cd $MCP_DIR; npm install; npm run build)"; return }
    Write-Info "installing MCP server dependencies (this may take a minute)"
    Push-Location $MCP_DIR
    try {
        Invoke-Npm @("install", "--silent", "--no-audit", "--no-fund", "--no-progress")
        if ($LASTEXITCODE -ne 0) { Write-Err "npm install failed in $MCP_DIR"; exit 1 }
        Write-Info "building MCP server"
        Invoke-Npm @("run", "build", "--silent")
        if ($LASTEXITCODE -ne 0) { Write-Err "npm run build failed in $MCP_DIR"; exit 1 }
    } finally { Pop-Location }
    $entry = Join-Path $MCP_DIR "dist/main.js"
    if (-not (Test-Path $entry)) {
        Write-Err "expected $entry after build, not found"; exit 1
    }
    Write-Ok "MCP server built at $entry"
}

# ---------- Skills ----------
function Install-SkillsForClient([string]$client) {
    $dest = Get-ClientSkillsDir $client
    if (-not $dest) { return }
    if ($DryRun) { Write-Dry "would link each skills/<name>/ into $dest/"; return }
    if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Force -Path $dest | Out-Null }

    $count = 0; $skipped = 0
    foreach ($skillDir in Get-ChildItem -Directory -Path (Join-Path $KIT_DIR "skills")) {
        $name = $skillDir.Name
        $link = Join-Path $dest $name
        $linkInfo = Get-Item -Force -ErrorAction SilentlyContinue $link
        if ($linkInfo -and $linkInfo.LinkType) {
            Remove-Item $link -Force
        } elseif (Test-Path $link) {
            Write-Warn2 "skipping $name (target $link exists and is not a symlink)"
            $skipped++
            continue
        }
        try {
            New-Item -ItemType SymbolicLink -Path $link -Target $skillDir.FullName -ErrorAction Stop | Out-Null
        } catch {
            # Symlinks on Windows require Developer Mode or admin. Fall back to copy.
            Write-Warn2 "symlink failed for $name (likely needs Developer Mode); copying instead"
            Copy-Item -Recurse -Force -Path $skillDir.FullName -Destination $link
        }
        $count++
    }
    $msg = "$(Get-ClientLabel $client): linked $count skills into $dest"
    if ($skipped -gt 0) { $msg += " ($skipped skipped)" }
    Write-Ok $msg
}

function Uninstall-SkillsForClient([string]$client) {
    $dest = Get-ClientSkillsDir $client
    if (-not $dest -or -not (Test-Path $dest)) { return }
    if ($DryRun) { Write-Dry "would remove kit skill symlinks from $dest/"; return }
    $count = 0
    foreach ($entry in Get-ChildItem -Force -Path $dest) {
        $info = Get-Item -Force $entry.FullName
        $isOurs = $false
        if ($info.LinkType -and $info.Target) {
            foreach ($t in @($info.Target)) {
                if ($t.StartsWith($KIT_DIR)) { $isOurs = $true; break }
            }
        }
        if ($isOurs) {
            Remove-Item -Force $entry.FullName
            $count++
        }
    }
    Write-Ok "$(Get-ClientLabel $client): removed $count skill symlinks from $dest"
}

# ---------- MCP entry ----------
function Get-EnvJsonHashtable([string]$conn, [string]$profileName) {
    $profiles = [ordered]@{ $profileName = [ordered]@{ authMode = "connectionString"; uri = $conn } }
    $profilesJson = ($profiles | ConvertTo-Json -Compress -Depth 10)
    # AUTH_REQUIRED gates ONLY the Entra-JWT bearer-token check on the MCP
    # server's HTTP/SSE transport (i.e., calls FROM the MCP client TO this
    # server). It is fully independent of MongoDB cluster auth: SCRAM
    # username/password from the URI and Entra-to-cluster tokens (when a
    # profile uses authMode=entra) flow through CONNECTION_PROFILES and stay
    # active regardless of this setting.
    #
    # The server defaults AUTH_REQUIRED=true and its startup validator fails
    # unless ENTRA_TENANT_ID / ENTRA_AUDIENCE are set. For local stdio we set
    # AUTH_REQUIRED=false (which short-circuits the Entra validator entirely)
    # and TRUST_LOCAL_STDIO=true (the upstream-recommended way to declare the
    # stdio process boundary trusted; previously named
    # ALLOW_UNAUTHENTICATED_STDIO before microsoft/documentdb-mcp#83).
    #
    # This is SAFE ONLY because TRANSPORT=stdio means the MCP server is a
    # subprocess on the user's trusted local machine — no network listener
    # is opened. If you ever switch TRANSPORT to streamable-http or sse, set
    # AUTH_REQUIRED=true and provide the Entra tenant/audience, or the /mcp
    # endpoint will be exposed unauthenticated.
    return [ordered]@{
        TRANSPORT           = "stdio"
        AUTH_REQUIRED       = "false"
        TRUST_LOCAL_STDIO   = "true"
        CONNECTION_PROFILES = $profilesJson
    }
}

function Install-McpForClient([string]$client, [string]$conn) {
    $cfg = Get-ClientMcpConfigPath $client
    $topKey = "mcpServers"
    $mainJs = Join-Path $MCP_DIR "dist/main.js"
    $envVars = Get-EnvJsonHashtable $conn $Profile
    Merge-McpEntry -ConfigPath $cfg -TopKey $topKey -ServerCommand "node" -ServerArgs @($mainJs) -EnvVars $envVars
    Write-Ok "$(Get-ClientLabel $client): wrote $MCP_ENTRY MCP entry → $cfg"
}

function Uninstall-McpForClient([string]$client) {
    $cfg = Get-ClientMcpConfigPath $client
    if (-not (Test-Path $cfg)) { return }
    Remove-McpEntry -ConfigPath $cfg -TopKey "mcpServers"
    Write-Ok "$(Get-ClientLabel $client): removed $MCP_ENTRY MCP entry from $cfg"
}

# ---------- Connection string ----------
function Resolve-Uri {
    if (-not [string]::IsNullOrWhiteSpace($script:Uri)) { return }
    if (-not [string]::IsNullOrWhiteSpace($env:DOCUMENTDB_URI)) {
        $script:Uri = $env:DOCUMENTDB_URI
        Write-Info "using `$env:DOCUMENTDB_URI"
        return
    }
    if ($Yes) {
        Write-Err "no connection string provided (use -Uri, or set `$env:DOCUMENTDB_URI)"
        exit 2
    }
    if (-not [Environment]::UserInteractive) {
        Write-Err "no connection string provided and not interactive"
        Write-Err "re-run with: -Uri 'mongodb://...'  OR  set `$env:DOCUMENTDB_URI"
        exit 2
    }
    Write-Heading "DocumentDB connection string"
    Write-Host "Examples:"
    Write-Host "  - Local:  mongodb://localhost:27017"
    Write-Host "  - Azure:  mongodb+srv://<user>:<pw>@<cluster>.mongocluster.cosmos.azure.com/?tls=true&authMechanism=SCRAM-SHA-256"
    $script:Uri = Read-Host "Connection string"
    if ([string]::IsNullOrWhiteSpace($script:Uri)) {
        Write-Err "connection string is required"; exit 2
    }
}

# ---------- Run ----------
function Invoke-Install {
    Write-Heading "documentdb-agent-kit installer"
    Write-Host "Install root: $INSTALL_ROOT"
    if ($DryRun) { Write-Warn2 "DRY RUN — no files will be modified" }

    Test-Prereqs

    $detected = Find-InstalledClients
    $clients = Filter-ClientsByUser $detected
    if (-not $clients -or $clients.Count -eq 0) {
        Write-Warn2 "no supported MCP clients detected"
        Write-Warn2 "supported: $($SUPPORTED_CLIENTS -join ', ')"
        exit 1
    }
    Write-Heading "Detected clients"
    foreach ($c in $clients) { Write-Host "  • $(Get-ClientLabel $c)" }

    if (-not $McpOnly) {
        Write-Heading "Installing agent kit"
        Sync-Repo $KIT_REPO $KIT_DIR $KitRef
        Write-Ok "kit at $KIT_DIR"
    }

    if (-not $SkillsOnly) {
        Write-Heading "Installing DocumentDB MCP server"
        Sync-Repo $MCP_REPO $MCP_DIR $McpRef
        Build-McpServer
        Resolve-Uri
    }

    Write-Heading "Wiring clients"
    foreach ($c in $clients) {
        if (-not $SkillsOnly) { Install-McpForClient $c $script:Uri }
        if (-not $McpOnly -and -not (Test-McpOnlyClient $c)) { Install-SkillsForClient $c }
    }

    Write-Heading "Done"
    Write-Host "Kit installed at: $KIT_DIR"
    if (-not $SkillsOnly) { Write-Host "MCP server at:    $(Join-Path $MCP_DIR 'dist/main.js')" }
    Write-Host ""
    Write-Host "Next steps:"
    Write-Host "  1. Fully quit and reopen each configured client."
    Write-Host "  2. Verify by asking the agent to list DocumentDB tools."
    Write-Host "     (Try: `"list_databases with connection_profile: $Profile`")"
    if (-not $McpOnly) {
        $hasMcpOnly = $false
        foreach ($c in $clients) { if (Test-McpOnlyClient $c) { $hasMcpOnly = $true; break } }
        if ($hasMcpOnly) {
            Write-Host ""
            Write-Host "  Note for Cursor / Copilot CLI / Gemini CLI:"
            Write-Host "  These clients discover skills from project-local files (AGENTS.md /"
            Write-Host "  GEMINI.md). To use the kit's skills in a project, copy or symlink:"
            Write-Host "    Copy-Item $KIT_DIR\AGENTS.md <your-project>\"
        }
    }
    Write-Host ""
    # `iex` does not accept -ArgumentList, so the irm | iex pipe form can't
    # take flags. Show the download-then-invoke form which actually works.
    Write-Host "Uninstall (one-liner):"
    Write-Host "    irm https://raw.githubusercontent.com/Azure/documentdb-agent-kit/main/install.ps1 -OutFile `$env:TEMP\install.ps1; & `$env:TEMP\install.ps1 -Uninstall -Yes"
    Write-Host "Or, from a local checkout:"
    Write-Host "    .\install.ps1 -Uninstall"
}

function Invoke-Uninstall {
    Write-Heading "Uninstalling documentdb-agent-kit"
    $detected = Find-InstalledClients
    $clients = Filter-ClientsByUser $detected
    foreach ($c in $clients) {
        try { Uninstall-McpForClient $c } catch { Write-Warn2 $_ }
        if (-not (Test-McpOnlyClient $c)) {
            try { Uninstall-SkillsForClient $c } catch { Write-Warn2 $_ }
        }
    }
    if (Test-Path $INSTALL_ROOT) {
        if ($DryRun) { Write-Dry "would remove $INSTALL_ROOT" }
        else {
            Remove-Item -Recurse -Force $INSTALL_ROOT
            Write-Ok "removed $INSTALL_ROOT"
        }
    }
    Write-Ok "uninstall complete"
}

if ($Uninstall) { Invoke-Uninstall } else { Invoke-Install }
