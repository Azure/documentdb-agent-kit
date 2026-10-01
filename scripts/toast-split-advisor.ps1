$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "invoke-diagnostic.ps1") `
    -Diagnostic "toast-split-advisor" @args
exit $LASTEXITCODE
