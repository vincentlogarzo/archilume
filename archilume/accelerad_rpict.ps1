<#
.SYNOPSIS
Simplified Accelerad Batch Renderer

.DESCRIPTION
Renders views using Accelerad with quality presets and GPU optimization

.PARAMETER OctreeName
Name of the octree file (without extension)

.PARAMETER Quality
Quality preset: draft, stand, prod, final, 4K, custom
Default: draft

.PARAMETER ViewName
Optional single view name to render. If omitted, renders all views.

.EXAMPLE
.\archilume\accelerad_rpict.ps1 -OctreeName "87Cowles_BLD_withWindows_with_site_TenK_cie_overcast" -Quality "draft" -ViewName "plan_ffl_093260"
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

Write-Host "`n============================================================================"
Write-Host "ACCELERAD BATCH RENDERER - STARTUP DIAGNOSTICS"
Write-Host "============================================================================"
Write-Host "Script Directory: $scriptDir"
Write-Host "Working Directory: $PWD"
Write-Host "Octree Name: $OctreeName"
Write-Host "Octree File: $octreeFile"
Write-Host "Quality: $Quality"
Write-Host "Resolution: $Resolution"
Write-Host "View Name: $(if ($ViewName) { $ViewName } else { '(All views)' })"
Write-Host "Accelerad Exe: $acceleradExe"
Write-Host "============================================================================`n"

if (-not (Test-Path $acceleradExe)) { throw "ERROR: Accelerad not found at $acceleradExe" }
if (-not (Test-Path $octreeFile)) { throw "ERROR: Octree not found at $octreeFile" }

# ============================================================================
# QUALITY PRESETS (Transposed Format)
# ============================================================================
#           draft   stand   prod    final   4k      custom  fast    med     high    detailed
$AA   = @(  0.01,   0.01,   0.01,   0.01,   0.01,   0.01,   0.06,   0.03,   0.01,   0       )
$AB   = @(  3,      3,      3,      3,      3,      8,      3,      3,      3,      2       )
$AD   = @(  2048,   1792,   1536,   1280,   1024,   2048,   512,    1024,   1536,   2048    )
$AS   = @(  1024,   896,    768,    640,    512,    1024,   256,    512,    512,    1024    )
$AR   = @(  1024,   1024,   1024,   1024,   1024,   1024,   128,    256,    512,    1024    )
$PS   = @(  4,      2,      2,      1,      1,      1,      2,      2,      1,      1       )
$PT   = @(  0.15,   0.12,   0.10,   0.07,   0.05,   0.05,   0.10,   0.08,   0.05,   0.02    )
$LR   = @(  5,      5,      5,      5,      5,      12,     12,     12,     12,     12      )
$LW   = @(  0.001,  0.001,  0.001,  0.001,  0.001,  0.0001, 0.001,  0.001,  0.001,  0.0001  )
$DJ   = @(  0.0,    0.5,    0.7,    0.9,    1.0,    0.7,    $null,  $null,  $null,  $null   )
$DS   = @(  0.25,   0.35,   0.50,   0.70,   0.90,   0.50,   $null,  $null,  $null,  $null   )
$DT   = @(  0.50,   0.35,   0.25,   0.15,   0.05,   0.25,   $null,  $null,  $null,  $null   )
$DC   = @(  0.25,   0.40,   0.50,   0.75,   0.90,   0.50,   $null,  $null,  $null,  $null   )
$DR   = @(  0,      1,      1,      2,      3,      1,      $null,  $null,  $null,  $null   )
$DP   = @(  512,    256,    256,    128,    64,     256,    $null,  $null,  $null,  $null   )

$qualities = @('draft', 'stand', 'prod', 'final', '4k', 'custom', 'fast', 'med', 'high', 'detailed')
$index = $qualities.IndexOf($Quality.ToLower())
if ($index -lt 0) { throw "Unknown quality: $Quality" }

$AA = $AA[$index]
$AB = $AB[$index]
$AD = $AD[$index]
$AS = $AS[$index]
$AR = $AR[$index]
$PS = $PS[$index]
$PT = $PT[$index]
$LR = $LR[$index]
$LW = $LW[$index]
$DJ = $DJ[$index]
$DS = $DS[$index]
$DT = $DT[$index]
$DC = $DC[$index]
$DR = $DR[$index]
$DP = $DP[$index]
$RES = if ($Resolution -gt 0) { $Resolution } else { 1024 }  # Default resolution
$RES_OV = 64
$AD_OV = [int]($AD * 1)
$AS_OV = [int]($AS * 1)


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
# TWO-PHASE RENDER LOOP (Optimized for GPU efficiency)
# ============================================================================
$batchStart = Get-Date

# Parse octree name: building_with_site_skyCondition
# Expected format: {building}_with_site_{sky} or just {building}_{sky}
if ($OctreeName -match '_with_site_') {
    $parts = $OctreeName -split '_with_site_', 2
    $building = $parts[0]
    $sky = $parts[1]
    Write-Host "Parsed octree name:"
    Write-Host "  Building: $building"
    Write-Host "  Sky: $sky"
} else {
    # Fallback: split on last underscore or use whole name
    Write-Host "WARNING: Octree name doesn't contain '_with_site_', using full name for building"
    $building = $OctreeName
    $sky = "unknown"
}

# Pre-compute file paths for all views
$viewData = @()
foreach ($viewFile in $views) {
    $viewNameOnly = $viewFile.BaseName
    $ambPath = "$imageDir/${building}_with_site_${viewNameOnly}__${sky}.amb"
    $hdrPath = "$imageDir/${building}_with_site_${viewNameOnly}__${sky}.hdr"

    $viewData += @{
        File = $viewFile
        Name = $viewNameOnly
        AmbFile = $ambPath
        HdrFile = $hdrPath
    }
}

# Show first view's file paths as example
if ($viewData.Count -gt 0) {
    Write-Host "`nExample file paths (first view):"
    Write-Host "  View: $($viewData[0].Name)"
    Write-Host "  AMB:  $($viewData[0].AmbFile)"
    Write-Host "  HDR:  $($viewData[0].HdrFile)"
    Write-Host ""
}

# ============================================================================
# PHASE 1: Generate ALL ambient files (minimize GPU context switches)
# ============================================================================
Write-Host "`n============================================================================"
Write-Host "PHASE 1/2: Generating ambient files for all views"
Write-Host "============================================================================`n"

$phase1Start = Get-Date
$current = 0
$ambGenerated = 0

foreach ($view in $viewData) {
    $current++

    # Skip if ambient file already exists
    if (Test-Path $view.AmbFile) {
        Write-Host "[$current/$($views.Count)] $($view.Name) - Ambient file exists, skipping"
        continue
    }

    Write-Host "[$current/$($views.Count)] $($view.Name)"
    Write-Host "  Generating ambient file: $($view.AmbFile)"

    # Verify view file exists
    if (-not (Test-Path $view.File.FullName)) {
        Write-Host "  ERROR: View file not found: $($view.File.FullName)"
        continue
    }

    # Verify octree file exists
    if (-not (Test-Path $octreeFile)) {
        Write-Host "  ERROR: Octree file not found: $octreeFile"
        continue
    }

    $overtureArgs = Get-RenderArgs $view.File.FullName $RES_OV $view.AmbFile $true

    # Redirect stdout to temp file, stderr will show progress
    $tempNull = [System.IO.Path]::Combine($env:TEMP, "rpict_null_$($view.Name).hdr")

    # Execute rendering (allow stderr to show progress, but don't treat it as error)
    $ErrorActionPreference = 'Continue'
    & $acceleradExe @overtureArgs > $tempNull 2>&1 | Out-Null
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'

    # Clean up temp file
    if (Test-Path $tempNull) { Remove-Item $tempNull -Force -ErrorAction SilentlyContinue }

    if ($exitCode -ne 0) {
        Write-Host "  WARNING: Ambient generation failed (exit code $exitCode)"
        Write-Host "  View file: $($view.File.FullName)"
        Write-Host "  Octree: $octreeFile"
    } elseif (-not (Test-Path $view.AmbFile)) {
        Write-Host "  ERROR: Ambient file was not created!"
        Write-Host "  Command: $acceleradExe $($overtureArgs -join ' ')"
    } else {
        $ambGenerated++
        Write-Host "  Success"
    }
    Write-Host ""
}

$phase1Elapsed = (Get-Date) - $phase1Start
Write-Host "============================================================================"
Write-Host ("Phase 1 Complete: Generated $ambGenerated new ambient files in {0}m {1}s" -f [math]::Floor($phase1Elapsed.TotalMinutes), $phase1Elapsed.Seconds)
Write-Host "============================================================================`n"

# ============================================================================
# PHASE 2: Render ALL main images (GPU stays warm throughout)
# ============================================================================
Write-Host "============================================================================"
Write-Host "PHASE 2/2: Main rendering for all views"
Write-Host "============================================================================`n"

$phase2Start = Get-Date
$current = 0
$rendered = 0
$skipped = 0

foreach ($view in $viewData) {
    $current++

    # Verify ambient file exists before rendering
    if (-not (Test-Path $view.AmbFile)) {
        Write-Host "[$current/$($views.Count)] $($view.Name) - SKIPPED: Missing ambient file"
        $skipped++
        continue
    }

    Write-Host "[$current/$($views.Count)] $($view.Name)"
    Write-Host "  Rendering ${RES}px: $($view.HdrFile)"

    $renderStart = Get-Date

    # Build render args (UseOV = false for main render)
    $renderArgs = Get-RenderArgs $view.File.FullName $RES $view.AmbFile $false

    # Quote paths for cmd.exe and use cmd.exe for proper binary stdout redirection (PowerShell > corrupts binary data)
    $renderArgs = $renderArgs | ForEach-Object {
        if ($_ -match '^[A-Za-z]:\\' -or $_ -match '\\') { "`"$_`"" } else { $_ }
    }
    $argsString = $renderArgs -join ' '
    cmd /c "`"$acceleradExe`" $argsString > `"$($view.HdrFile)`""

    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ERROR: Render failed (exit code $LASTEXITCODE)"
    } else {
        $rendered++
        $elapsed = (Get-Date) - $renderStart
        Write-Host ("  Complete: {0}m {1}s" -f [math]::Floor($elapsed.TotalMinutes), $elapsed.Seconds)
    }
    Write-Host ""
}

$phase2Elapsed = (Get-Date) - $phase2Start
Write-Host "============================================================================"
Write-Host ("Phase 2 Complete: Rendered $rendered views in {0}m {1}s" -f [math]::Floor($phase2Elapsed.TotalMinutes), $phase2Elapsed.Seconds)
if ($skipped -gt 0) {
    Write-Host "WARNING: Skipped $skipped views due to missing ambient files"
}
Write-Host "============================================================================`n"

# Final summary
$totalElapsed = (Get-Date) - $batchStart
Write-Host "============================================================================"
Write-Host "BATCH RENDERING COMPLETE"
Write-Host "============================================================================"
Write-Host "Total views processed: $($views.Count)"
Write-Host "Ambient files generated: $ambGenerated"
Write-Host "Main renders completed: $rendered"
Write-Host ("Phase 1 time: {0}m {1}s" -f [math]::Floor($phase1Elapsed.TotalMinutes), $phase1Elapsed.Seconds)
Write-Host ("Phase 2 time: {0}m {1}s" -f [math]::Floor($phase2Elapsed.TotalMinutes), $phase2Elapsed.Seconds)
Write-Host ("Total time: {0}m {1}s" -f [math]::Floor($totalElapsed.TotalMinutes), $totalElapsed.Seconds)
Write-Host "============================================================================"
