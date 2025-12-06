<#
.SYNOPSIS
Simplified Accelerad Batch Renderer

.DESCRIPTION
Renders views using Accelerad with quality presets and GPU optimization

.PARAMETER Octree
Name of the octree file (without extension)

.PARAMETER Qual
Quality preset: draft, stand, prod, final, 4K, custom
Default: draft

.PARAMETER View
Optional single view name to render. If omitted, renders all views.

.EXAMPLE
.\archilume\accelerad_rpict.ps1 -Octree "87Cowles_BLD_withWindows_with_site_TenK_cie_overcast" -Qual "draft" -View "plan_ffl_093260"
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true, Position=0, HelpMessage="Octree name (without .oct extension)")]
    [ValidateNotNullOrEmpty()]
    [string]$OctreeName,

    [Parameter(Position=1)]
    [ValidateSet('draft','stand','prod','final','4K','custom','fast','med','high','detailed', IgnoreCase=$true)]
    [string]$Quality = 'draft',

    [Parameter(Position=2)]
    [ValidateRange(128, 8192)]
    [int]$Resolution = 0,

    [Parameter(Position=3)]
    [string]$ViewName
)

$ErrorActionPreference = 'Stop'

# ============================================================================
# SETUP PATHS
# ============================================================================
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$acceleradExe = Join-Path $scriptDir '../.devcontainer/accelerad_07_beta_Windows/bin/accelerad_rpict.exe'
$octreeFile = "outputs/octree/$OctreeName.oct"
$viewDir = 'outputs/view'
$imageDir = 'outputs/image'

if (-not (Test-Path $acceleradExe)) { throw "ERROR: Accelerad not found at $acceleradExe" }
if (-not (Test-Path $octreeFile)) { throw "ERROR: Octree not found at $octreeFile" }

# ============================================================================
# QUALITY PRESETS
# ============================================================================
# Quality presets: [AA, AB, AD, AS, AR, PS, PT, LR, LW, DJ, DS, DT, DC, DR, DP]
$presets = @{
    'draft'    = @(0.01, 3, 2048, 1024, 1024, 4, 0.15, 5, 0.001, 0.0, 0.25, 0.50, 0.25, 0, 512)
    'stand'    = @(0.01, 3, 1792,  896, 1024, 2, 0.12, 5, 0.001, 0.5, 0.35, 0.35, 0.40, 1, 256)
    'prod'     = @(0.01, 3, 1536,  768, 1024, 2, 0.10, 5, 0.001, 0.7, 0.50, 0.25, 0.50, 1, 256)
    'final'    = @(0.01, 3, 1280,  640, 1024, 1, 0.07, 5, 0.001, 0.9, 0.70, 0.15, 0.75, 2, 128)
    '4k'       = @(0.01, 3, 1024,  512, 1024, 1, 0.05, 5, 0.001, 1.0, 0.90, 0.05, 0.90, 3,  64)
    'custom'   = @(0.01, 8, 2048, 1024, 1024, 1, 0.05,12, 0.0001,0.7, 0.50, 0.25, 0.50, 1, 256)
    'fast'     = @(0.06, 3,  512,  256,  128, 2, 0.10,12, 0.001, $null, $null, $null, $null, $null, $null)
    'med'      = @(0.03, 3, 1024,  512,  256, 2, 0.08,12, 0.001, $null, $null, $null, $null, $null, $null)
    'high'     = @(0.01, 3, 1536,  512,  512, 1, 0.05,12, 0.001, $null, $null, $null, $null, $null, $null)
    'detailed' = @(0,    1, 2048, 1024, 1024, 1, 0.02,12, 0.0001,$null, $null, $null, $null, $null, $null)
}

$p = $presets[$Quality.ToLower()]
if (-not $p) { throw "Unknown quality: $Quality" }

$AA, $AB, $AD, $AS, $AR, $PS, $PT, $LR, $LW, $DJ, $DS, $DT, $DC, $DR, $DP = $p
$RES = if ($Resolution -gt 0) { $Resolution } else { 1024 }  # Default resolution
$RES_OV = 64
$AD_OV = [int]($AD * 1.75)
$AS_OV = [int]($AS * 1.75)


# ============================================================================
# GPU CONFIGURATION
# ============================================================================
Write-Host "Checking for GPU..."
try {
    $gpuVramMB = nvidia-smi --query-gpu=memory.total --format=csv,nounits,noheader 2>$null | Select-Object -First 1
    if ($gpuVramMB -match '^\d+$') {
        $gpuVramGB = [math]::Floor($gpuVramMB / 1024)
        $cacheMB = [math]::Min([math]::Floor($gpuVramMB * 0.3), 16384)
        $env:CUDA_CACHE_MAXSIZE = $cacheMB * 1024 * 1024
        $env:CUDA_CACHE_DISABLE = 0
        $env:CUDA_FORCE_PTX_JIT = 1
        Write-Host "GPU: $gpuVramGB GB ($gpuVramMB MB), Cache: $cacheMB MB"
    } else { throw }
} catch {
    Write-Host "WARNING: GPU not detected, using defaults"
    $env:CUDA_CACHE_MAXSIZE = 1073741824
    $env:CUDA_CACHE_DISABLE = 0
    $env:CUDA_FORCE_PTX_JIT = 1
}

# ============================================================================
# FIND VIEWS TO RENDER
# ============================================================================
$views = if ($ViewName) {
    $viewPath = Join-Path $viewDir "$ViewName.vp"
    if (-not (Test-Path $viewPath)) { throw "ERROR: View file not found: $viewPath" }
    Write-Host "Mode: Single view '$ViewName'"
    @(Get-Item $viewPath)
} else {
    Write-Host "Mode: Batch render ALL views"
    @(Get-ChildItem "$viewDir\*.vp")
}

if ($views.Count -eq 0) { throw "ERROR: No view files found in $viewDir" }
Write-Host "Found $($views.Count) view(s), Quality: $Quality, Resolution: ${RES}px`n"

# ============================================================================
# RENDER ARGUMENT BUILDER
# ============================================================================
function Get-RenderArgs($ViewPath, $Res, $AmbFile, $UseOV = $false) {
    $ad = if ($UseOV) { $AD_OV } else { $AD }
    $as = if ($UseOV) { $AS_OV } else { $AS }

    $cmdArgs = @('-w', '-t', '1', '-vf', $ViewPath, '-x', $Res, '-y', $Res)
    $cmdArgs += @('-aa', $AA, '-ab', $AB, '-ad', $ad, '-as', $as, '-ar', $AR)
    if ($null -ne $PS) { $cmdArgs += @('-ps', $PS) }
    if ($null -ne $PT) { $cmdArgs += @('-pt', $PT) }
    if ($null -ne $LR) { $cmdArgs += @('-lr', $LR) }
    if ($null -ne $LW) { $cmdArgs += @('-lw', $LW) }
    if ($null -ne $DJ) { $cmdArgs += @('-dj', $DJ) }
    if ($null -ne $DS) { $cmdArgs += @('-ds', $DS) }
    if ($null -ne $DT) { $cmdArgs += @('-dt', $DT) }
    if ($null -ne $DC) { $cmdArgs += @('-dc', $DC) }
    if ($null -ne $DR) { $cmdArgs += @('-dr', $DR) }
    if ($null -ne $DP) { $cmdArgs += @('-dp', $DP) }
    $cmdArgs += @('-i', '-af', $AmbFile, $octreeFile)
    return $cmdArgs
}

# ============================================================================
# RENDER LOOP
# ============================================================================
$batchStart = Get-Date
$current = 0

foreach ($viewFile in $views) {
    $current++
    $viewNameOnly = $viewFile.BaseName
    Write-Host "[$current/$($views.Count)] $viewNameOnly"

    # Parse octree name: building_with_site_skyCondition
    $building, $sky = $OctreeName -split '_with_site_', 2

    # Output paths
    $ambFile = "$imageDir/${building}_with_site_${viewNameOnly}__${sky}.amb"
    $hdrFile = "$imageDir/${building}_with_site_${viewNameOnly}__${sky}.hdr"

    $renderStart = Get-Date

    # Overture (generate ambient file if missing)
    if (-not (Test-Path $ambFile)) {
        Write-Host "-------------------------------------------------------------------"
        Write-Host "  Overture: Generating ambient file"
        Write-Host "  AMB_FILE: $ambFile"
        Write-Host "-------------------------------------------------------------------"

        $overtureArgs = Get-RenderArgs $viewFile.FullName $RES_OV $ambFile $true
        & $acceleradExe @overtureArgs | Out-Null

        if ($LASTEXITCODE -ne 0) { Write-Host "  Warning: Overture failed, continuing..." }
        if (-not (Test-Path $ambFile)) { Write-Host "  ERROR: Ambient file was not created!" }
    }

    # Main render
    Write-Host "-------------------------------------------------------------------"
    Write-Host "  Render: $viewNameOnly in ${RES}px"
    Write-Host "  HDR_FILE: $hdrFile"
    Write-Host "-------------------------------------------------------------------"

    # Build render args (UseOV = false for main render)
    $renderArgs = Get-RenderArgs $viewFile.FullName $RES $ambFile $false

    # Quote paths for cmd.exe and use cmd.exe for proper binary stdout redirection (PowerShell > corrupts binary data)
    $renderArgs = $renderArgs | ForEach-Object {
        if ($_ -match '^[A-Za-z]:\\' -or $_ -match '\\') { "`"$_`"" } else { $_ }
    }
    $argsString = $renderArgs -join ' '
    cmd /c "`"$acceleradExe`" $argsString > `"$hdrFile`""

    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ERROR: Render failed"
    } else {
        $elapsed = (Get-Date) - $renderStart
        Write-Host ("  Complete: {0}m {1}s" -f [math]::Floor($elapsed.TotalMinutes), $elapsed.Seconds)
    }
    Write-Host ""
}

# Final summary
$totalElapsed = (Get-Date) - $batchStart
Write-Host "============================================================================"
Write-Host ("Batch complete: $($views.Count) views in {0}m {1}s" -f [math]::Floor($totalElapsed.TotalMinutes), $totalElapsed.Seconds)
Write-Host "============================================================================"
