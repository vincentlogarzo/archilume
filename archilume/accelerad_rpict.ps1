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
    [Parameter(Mandatory = $true, Position = 0, HelpMessage = "Octree name (without .oct extension)")]
    [ValidateNotNullOrEmpty()]
    [string]
    $OctreeName,

    [Parameter(Position = 1)]
    [ValidateSet('draft', 'stand', 'prod', 'final', '4K', 'custom', 'fast', 'med', 'high', 'detailed', IgnoreCase = $true)]
    [string]
    $Quality = 'draft',

    [Parameter(Position = 2)]
    [ValidateRange(128, 8192)]
    [int]
    $Resolution = 0,

    [Parameter(Position = 3)]
    [string]
    $ViewName
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
Write-Host "Octree Path: $octreeFile"
Write-Host "View Path: $viewDir"
Write-Host "Quality: $Quality"
Write-Host "Resolution: $Resolution"
Write-Host "Accelerad Exe: $acceleradExe"
Write-Host "============================================================================`n"

if (-not (Test-Path $acceleradExe)) { throw "ERROR: Accelerad not found at $acceleradExe" }
if (-not (Test-Path $octreeFile)) { throw "ERROR: Octree not found at $octreeFile" }

# QUALITY PRESETS (Transposed Format)
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
$q = $qualities.IndexOf($Quality.ToLower())
if ($q -lt 0) { throw "Unknown quality: $Quality" }

# Extract values for selected quality
$AA, $AB, $AD, $AS, $AR, $PS, $PT, $LR, $LW, $DJ, $DS, $DT, $DC, $DR, $DP =
    $AA[$q], $AB[$q], $AD[$q], $AS[$q], $AR[$q], $PS[$q], $PT[$q], $LR[$q], $LW[$q], $DJ[$q], $DS[$q], $DT[$q], $DC[$q], $DR[$q], $DP[$q]
$RES = if ($Resolution -gt 0) { $Resolution } else { 1024 }  # Default resolution

# GPU CONFIGURATION
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

# FIND VIEWS TO RENDER
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

# RENDER ARGUMENT BUILDER
function Get-RenderArgs($ViewPath, $Res, $AmbFile) {
    # Build base arguments
    $cmdArgs = @('-w', '-t', '1', '-vf', $ViewPath, '-x', $Res, '-y', $Res,
                 '-aa', $AA, '-ab', $AB, '-ad', $AD, '-as', $AS, '-ar', $AR)

    # Add optional parameters (only if not null)
    if ($null -ne $PS) { $cmdArgs += '-ps', $PS }
    if ($null -ne $PT) { $cmdArgs += '-pt', $PT }
    if ($null -ne $LR) { $cmdArgs += '-lr', $LR }
    if ($null -ne $LW) { $cmdArgs += '-lw', $LW }
    if ($null -ne $DJ) { $cmdArgs += '-dj', $DJ }
    if ($null -ne $DS) { $cmdArgs += '-ds', $DS }
    if ($null -ne $DT) { $cmdArgs += '-dt', $DT }
    if ($null -ne $DC) { $cmdArgs += '-dc', $DC }
    if ($null -ne $DR) { $cmdArgs += '-dr', $DR }
    if ($null -ne $DP) { $cmdArgs += '-dp', $DP }

    # Add final arguments
    $cmdArgs += '-i', '-af', $AmbFile, $octreeFile
    return $cmdArgs
}

Write-Host "============================================================================"
Write-Host "GPU RENDERING - All views"
Write-Host "============================================================================`n"

$renderStart = Get-Date
$current = 0
$rendered = 0

foreach ($viewFile in $views) {
    $current++
    $viewName = $viewFile.BaseName

    # Generate output paths
    $ambFile = "$imageDir/${OctreeName}_${viewName}.amb"
    $hdrFile = "$imageDir/${OctreeName}_${viewName}.hdr"

    Write-Host "[$current/$($views.Count)] $viewName"
    Write-Host "  Rendering ${RES}px: $hdrFile"

    $viewRenderStart = Get-Date

    # Build render args
    $renderArgs = Get-RenderArgs $viewFile.FullName $RES $ambFile

    # Quote paths for cmd.exe and use cmd.exe for proper binary stdout redirection (PowerShell > corrupts binary data)
    $renderArgs = $renderArgs | ForEach-Object {
        if ($_ -match '^[A-Za-z]:\\' -or $_ -match '\\') { "`"$_`"" } else { $_ }
    }
    $argsString = $renderArgs -join ' '
    cmd /c "`"$acceleradExe`" $argsString > `"$hdrFile`""

    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ERROR: Render failed (exit code $LASTEXITCODE)"
    } else {
        $rendered++
        $elapsed = (Get-Date) - $viewRenderStart
        Write-Host ("  Complete: {0}m {1}s" -f [math]::Floor($elapsed.TotalMinutes), $elapsed.Seconds)
    }
    Write-Host ""
}

$renderElapsed = (Get-Date) - $renderStart
Write-Host "============================================================================"
Write-Host ("Rendering Complete: $rendered views in {0}m {1}s" -f [math]::Floor($renderElapsed.TotalMinutes), $renderElapsed.Seconds)
Write-Host "============================================================================"
