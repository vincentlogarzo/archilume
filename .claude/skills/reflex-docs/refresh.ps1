#!/usr/bin/env pwsh
# Pull Reflex framework docs into the local skill reference directory.
# Sources: reflex.dev/llms.txt (LLM-optimised) + reflex-web repo docs/ (markdown).
# Usage: powershell -File .claude/skills/reflex-docs/refresh.ps1

$ErrorActionPreference = "Stop"

$targetDir = [System.IO.Path]::GetFullPath("$PSScriptRoot\reference")
$tempDir   = Join-Path $env:TEMP "reflex-web-sparse"

Write-Host "Target: $targetDir"

# Clean previous reference
if (Test-Path $targetDir) { Remove-Item $targetDir -Recurse -Force }
New-Item -ItemType Directory -Path $targetDir -Force | Out-Null

# 1. Download llms.txt (LLM-optimised overview of Reflex basics)
Write-Host "Downloading llms.txt..."
Invoke-WebRequest -Uri "https://reflex.dev/llms.txt" -OutFile "$targetDir\llms.txt"

# 2. Sparse clone reflex-web docs/ (tutorials, getting-started)
Write-Host "Cloning reflex-web docs/..."
if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force }
git clone --depth 1 --filter=blob:none --sparse https://github.com/reflex-dev/reflex-web.git $tempDir
Push-Location $tempDir
git sparse-checkout set docs
Pop-Location

New-Item -ItemType Directory -Path "$targetDir\reflex-web-docs" -Force | Out-Null
Copy-Item -Path "$tempDir\docs\*" -Destination "$targetDir\reflex-web-docs" -Recurse

# Cleanup temp
Remove-Item $tempDir -Recurse -Force

$count = (Get-ChildItem -Path $targetDir -Recurse -File).Count
Write-Host "Done. $count files pulled into $targetDir"
