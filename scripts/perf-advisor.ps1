$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "invoke-diagnostic.ps1") `
    -Diagnostic "perf-advisor" @args
exit $LASTEXITCODE
