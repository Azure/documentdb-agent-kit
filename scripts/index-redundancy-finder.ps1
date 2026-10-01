$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "invoke-diagnostic.ps1") `
    -Diagnostic "index-redundancy-finder" @args
exit $LASTEXITCODE
