#Requires -Version 5.1
<#
.SYNOPSIS
  Builds dist\archilume.zip for team distribution.

.DESCRIPTION
  Stages:
    - docker\launch-archilume.cmd    (double-click entry point)
    - docker\launch-archilume.ps1
    - docker\docker-compose-archilume.yml
    - docker\README.md
    - docker\demos\demo-sunlight\  -> projects\demo-sunlight\
    - docker\demos\demo-daylight\  -> projects\demo-daylight\
  into a temp folder, then Compress-Archive into docker\dist\archilume.zip.

  Demo content is curated in-tree under docker\demos\ so the shipped payload is
  reviewable in git and stays small. To update a demo, edit the files under
  docker\demos\ directly.
#>

[CmdletBinding()]
param(
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$DistDir = Join-Path $PSScriptRoot 'dist'
if (-not $OutputPath) { $OutputPath = Join-Path $DistDir 'archilume.zip' }

$LauncherCmd = Join-Path $PSScriptRoot 'launch-archilume.cmd'
$LauncherPs1 = Join-Path $PSScriptRoot 'launch-archilume.ps1'
$ReadmeMd    = Join-Path $PSScriptRoot 'README.md'
$ComposeYml  = Join-Path $PSScriptRoot 'docker-compose-archilume.yml'

$DemosRoot   = Join-Path $PSScriptRoot 'demos'
$SunlightSrc = Join-Path $DemosRoot    'demo-sunlight'
$DaylightSrc = Join-Path $DemosRoot    'demo-daylight'

foreach ($path in @($LauncherCmd, $LauncherPs1, $ReadmeMd, $ComposeYml, $SunlightSrc, $DaylightSrc)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing expected file or folder: $path"
    }
}

# Staging area inside system temp so the working copy never lands in the repo.
$Staging = Join-Path ([System.IO.Path]::GetTempPath()) ("archilume-zip-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Staging | Out-Null

try {
    Write-Host "Staging at $Staging" -ForegroundColor Cyan

    Copy-Item -LiteralPath $LauncherCmd -Destination $Staging
    Copy-Item -LiteralPath $LauncherPs1 -Destination $Staging
    Copy-Item -LiteralPath $ReadmeMd    -Destination $Staging
    Copy-Item -LiteralPath $ComposeYml  -Destination $Staging

    $stagedProjects = Join-Path $Staging 'projects'
    New-Item -ItemType Directory -Path $stagedProjects | Out-Null

    Write-Host "  + demo-sunlight  (from docker\demos\demo-sunlight)" -ForegroundColor Gray
    Copy-Item -LiteralPath $SunlightSrc -Destination (Join-Path $stagedProjects 'demo-sunlight') -Recurse

    Write-Host "  + demo-daylight  (from docker\demos\demo-daylight)" -ForegroundColor Gray
    Copy-Item -LiteralPath $DaylightSrc -Destination (Join-Path $stagedProjects 'demo-daylight') -Recurse

    # Prepare output path.
    $outDir = Split-Path -Parent $OutputPath
    if (-not (Test-Path -LiteralPath $outDir)) {
        New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    }
    if (Test-Path -LiteralPath $OutputPath) {
        Remove-Item -LiteralPath $OutputPath -Force
    }

    Write-Host "Compressing -> $OutputPath" -ForegroundColor Cyan
    # Wildcard ensures the zip's top level contains launch-archilume.cmd,
    # launch-archilume.ps1, README.md, docker-compose-archilume.yml, and
    # projects\ (no extra wrapping folder).
    Compress-Archive -Path (Join-Path $Staging '*') -DestinationPath $OutputPath -CompressionLevel Optimal

    $size = (Get-Item -LiteralPath $OutputPath).Length
    $sizeMb = [Math]::Round($size / 1MB, 2)
    Write-Host ""
    Write-Host "Built archilume.zip ($sizeMb MB)" -ForegroundColor Green
    Write-Host "  Path: $OutputPath"
} finally {
    if (Test-Path -LiteralPath $Staging) {
        Remove-Item -LiteralPath $Staging -Recurse -Force -ErrorAction SilentlyContinue
    }
}
