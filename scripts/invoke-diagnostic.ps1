param(
    [Parameter(Mandatory = $true)]
    [string]$Diagnostic,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$DiagnosticArgs
)

$ErrorActionPreference = "Stop"
$ScriptPath = Join-Path $PSScriptRoot "$Diagnostic.py"

$PyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($PyLauncher) {
    & $PyLauncher.Source -3 -c "import sys; raise SystemExit(sys.version_info < (3, 10))"
    if ($LASTEXITCODE -eq 0) {
        & $PyLauncher.Source -3 $ScriptPath @DiagnosticArgs
        exit $LASTEXITCODE
    }
}

$Python = Get-Command python -ErrorAction SilentlyContinue
if ($Python) {
    & $Python.Source -c "import sys; raise SystemExit(sys.version_info < (3, 10))"
    if ($LASTEXITCODE -eq 0) {
        & $Python.Source $ScriptPath @DiagnosticArgs
        exit $LASTEXITCODE
    }
}

Write-Error "Python 3.10 or newer is required. Install Python and ensure 'py' or 'python' is on PATH."
exit 1
