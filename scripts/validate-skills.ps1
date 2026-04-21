#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Validate that every skill under skills/ has a SKILL.md with valid front matter.

.DESCRIPTION
  Checks:
    1. Every skills/<name>/ contains a SKILL.md file.
    2. SKILL.md begins with a YAML front-matter block delimited by `---`.
    3. Front matter contains non-empty `name` and `description` keys.
    4. `name` values are unique across all skills.

.EXAMPLE
  pwsh ./scripts/validate-skills.ps1
#>

param(
  [string]$SkillsRoot = (Join-Path $PSScriptRoot ".." "skills")
)

$ErrorActionPreference = "Stop"
$errors = @()
$names  = @{}

if (-not (Test-Path $SkillsRoot)) {
  Write-Error "Skills directory not found: $SkillsRoot"
  exit 1
}

$skillDirs = Get-ChildItem -Path $SkillsRoot -Directory | Sort-Object Name

if (-not $skillDirs) {
  Write-Error "No skill folders found under $SkillsRoot"
  exit 1
}

foreach ($dir in $skillDirs) {
  $skillPath = Join-Path $dir.FullName "SKILL.md"
  $rel = "skills/$($dir.Name)/SKILL.md"

  if (-not (Test-Path $skillPath)) {
    $errors += "[$rel] missing SKILL.md"
    continue
  }

  $content = Get-Content -Path $skillPath -Raw

  # Front matter: file must start with `---\n ... \n---`
  $match = [regex]::Match($content, '^\s*---\s*\r?\n(?<body>[\s\S]*?)\r?\n---\s*\r?\n')
  if (-not $match.Success) {
    $errors += "[$rel] missing or malformed YAML front matter (must start with --- and close with ---)"
    continue
  }

  $fm = $match.Groups["body"].Value

  $nameMatch = [regex]::Match($fm, '(?m)^name\s*:\s*(?<v>.+?)\s*$')
  $descMatch = [regex]::Match($fm, '(?ms)^description\s*:\s*(?<v>(?:>-|\|)?\s*\S.*?)(?=^\w[\w-]*\s*:|\z)')

  if (-not $nameMatch.Success -or [string]::IsNullOrWhiteSpace($nameMatch.Groups["v"].Value)) {
    $errors += "[$rel] front matter is missing a non-empty 'name:' field"
  } else {
    $n = $nameMatch.Groups["v"].Value.Trim().Trim('"').Trim("'")
    if ($names.ContainsKey($n)) {
      $errors += "[$rel] duplicate skill name '$n' (also used by skills/$($names[$n])/SKILL.md)"
    } else {
      $names[$n] = $dir.Name
    }
  }

  if (-not $descMatch.Success -or [string]::IsNullOrWhiteSpace($descMatch.Groups["v"].Value)) {
    $errors += "[$rel] front matter is missing a non-empty 'description:' field"
  }
}

Write-Host ""
Write-Host "Validated $($skillDirs.Count) skill folder(s) under $SkillsRoot" -ForegroundColor Cyan

if ($errors.Count -gt 0) {
  Write-Host ""
  Write-Host "FAILED - $($errors.Count) issue(s):" -ForegroundColor Red
  foreach ($e in $errors) { Write-Host "  - $e" -ForegroundColor Red }
  exit 1
}

Write-Host ""
Write-Host "OK - all skills have valid front matter with unique names." -ForegroundColor Green
Write-Host "Skills:" -ForegroundColor Cyan
$names.GetEnumerator() | Sort-Object Name | ForEach-Object {
  Write-Host ("  - {0,-45} -> skills/{1}/" -f $_.Key, $_.Value)
}
exit 0
