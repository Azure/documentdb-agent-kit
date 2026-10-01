$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "invoke-diagnostic.ps1") `
    -Diagnostic "document-bloat-advisor" @args
exit $LASTEXITCODE
