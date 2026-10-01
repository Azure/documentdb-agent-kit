$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "invoke-diagnostic.ps1") `
    -Diagnostic "db-config-advisor" @args
exit $LASTEXITCODE
