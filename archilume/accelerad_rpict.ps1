<#
.SYNOPSIS
Simplified Accelerad Batch Renderer

.DESCRIPTION
Renders views using Accelerad with quality presets and GPU optimization

.PARAMETER Octree
Name of the octree file (without extension)

.PARAMETER Qual
Quality preset: prev, draft, stand, prod, final, 4K, custom
Default: prev

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
    [ValidateSet('draft','stand','prod','final','4K','custom', IgnoreCase=$true)]
    [string]$Quality = 'prev',

    [Parameter(Position=2)]
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
$RES_OV, $AA_OV, $AB_OV, $AD_OV, $AR_OV = 512, 0.01, 3, 2048, 1024
$AS_OV = [int]($AD_OV * 0.5)
$LR_AMB = $AB_OV + 2

# AD distribution: draft=100% AD_OV, 4K=50% AD_OV, evenly distributed in between
# Format:         RES,   AA,  AB,     AD,                   AS,                 AR,    PS, PT,   LR,      LW,     DJ,  DS,   DT,   DC,  DR, DP
$presets = @{
    'draft'     = 768,  0.01, $AB_OV, [int]($AD_OV*1.000), [int]($AS_OV*1.000), $AR_OV, 4, 0.15, $LR_AMB, 0.0010, 0.0, 0.25, 0.50, 0.25, 0, 512
    'stand'     = 1024, 0.01, $AB_OV, [int]($AD_OV*0.875), [int]($AS_OV*1.000), $AR_OV, 2, 0.12, $LR_AMB, 0.0010, 0.5, 0.35, 0.35, 0.40, 1, 256
    'prod'      = 1536, 0.01, $AB_OV, [int]($AD_OV*0.750), [int]($AS_OV*1.000), $AR_OV, 2, 0.10, $LR_AMB, 0.0010, 0.7, 0.50, 0.25, 0.50, 1, 256
    'final'     = 2048, 0.01, $AB_OV, [int]($AD_OV*0.625), [int]($AS_OV*1.000), $AR_OV, 1, 0.07, $LR_AMB, 0.0010, 0.9, 0.70, 0.15, 0.75, 2, 128 
    '4K'        = 4096, 0.01, $AB_OV, [int]($AD_OV*0.500), [int]($AS_OV*1.000), $AR_OV, 1, 0.05, $LR_AMB, 0.0010, 1.0, 0.90, 0.05, 0.90, 3, 64   
    'custom'    = 1024, 0.01, 8,      4096,                [int]($AS_OV*1.000), 1024,   2, 0.05, 12,      0.0001, 0.7, 0.50, 0.25, 0.50, 1, 256
}

$params = $presets[$Quality.ToLower()]
$RES, $AA, $AB, $AD, $AS, $AR, $PS, $PT, $LR, $LW, $DJ, $DS, $DT, $DC, $DR, $DP = $params


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

        & $acceleradExe -w -t 1 -vf $viewFile.FullName -x $RES_OV -y $RES_OV `
            -aa $AA_OV -ab $AB_OV -ad $AD_OV -as $AS_OV -ar $AR_OV `
            -ps $PS -pt $PT -lr $LR_AMB -lw $LW `
            -dj $DJ -ds $DS -dt $DT -dc $DC -dr $DR -dp $DP `
            -i -af $ambFile $octreeFile | Out-Null

        if ($LASTEXITCODE -ne 0) { Write-Host "  Warning: Overture failed, continuing..." }
        if (-not (Test-Path $ambFile)) { Write-Host "  ERROR: Ambient file was not created!" }
    }

    # Main render
    Write-Host "-------------------------------------------------------------------"
    Write-Host "  Render: $viewNameOnly in ${RES}px"
    Write-Host "  HDR_FILE: $hdrFile"
    Write-Host "-------------------------------------------------------------------"

    # Use cmd.exe for proper binary stdout redirection (PowerShell > corrupts binary data)
    cmd /c "`"$acceleradExe`" -w -t 1 -vf `"$($viewFile.FullName)`" -x $RES -y $RES -aa $AA -ab $AB -ad $AD -as $AS -ar $AR -ps $PS -pt $PT -lr $LR -lw $LW -dj $DJ -ds $DS -dt $DT -dc $DC -dr $DR -dp $DP -i -af `"$ambFile`" `"$octreeFile`" > `"$hdrFile`""

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
