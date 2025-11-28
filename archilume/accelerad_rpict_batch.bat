@echo off
setlocal enabledelayedexpansion
REM Usage: accelerad_renderer_batch.bat [OCTREE_NAME] [QUALITY] [RES] [VIEW_NAME]
REM Example (all views): .\archilume\accelerad_rpict_batch.bat octree detailed 2048
REM Example (single view): .\archilume\accelerad_rpict_batch.bat octree detailed 2048 plan_L01
REM If VIEW_NAME is omitted, ALL view files in outputs/views_grids/ will be rendered
REM Quality options: fast, med, high, detailed, test, ark
REM .\archilume\accelerad_rpict_batch.bat 87Cowles_BLD_withWindows_with_site_TenK_cie_overcast fast 512 plan_L02


REM Arguments
set OCTREE_NAME=%1
set QUALITY=%2
set RES=%3
set SINGLE_VIEW=%4

if "%OCTREE_NAME%"=="" (
    echo Error: OCTREE_NAME required
    echo Usage: accelerad_renderer_batch.bat [OCTREE_NAME] [QUALITY] [RES] [VIEW_NAME]
    echo Quality options: fast, med, high, detailed, test, ark
    echo Example all views: .\archilume\accelerad_rpict_batch.bat octree high 512
    echo Example single view: .\archilume\accelerad_renderer_batch.bat octree detailed 2048 plan_L01
    exit /b 1
)

REM Set default quality and resolution
if "%QUALITY%"=="" set QUALITY=fast
if "%RES%"=="" set RES=1024

REM Configuration
set OCTREE=outputs/octree/%OCTREE_NAME%.oct
set VIEWS_DIR=outputs/views_grids

REM Quality preset definitions:
REM                           AA    AB    AD    AS    AR   PS   PT     LR   LW
set "PRESET_fast=           0.07    3   1024   256   124    2   0.1    12   0.001"
set "PRESET_med=            0.05    3   1024   256   512    2   0.1    12   0.001"
set "PRESET_high=           0.01    3   1024   512   512    2   0.1    12   0.001"
set "PRESET_detailed=       0       1   2048  1024   124    1   0.02   12   0.0001"
set "PRESET_test=           0.05    8   1024   256   512    2   0.12   12   0.0005"
set "PRESET_ark=            0.01    8   4096  1024  1024    4   0.05   16   0.0002"
REM AA=ambient accuracy, AB=ambient bounces, AD=ambient divisions, AS=ambient super-samples
REM AR=ambient resolution, PS=pixel sample, PT=pixel threshold, LR=limit reflection, LW=limit weight

REM Validate and load selected preset
if /i "%QUALITY%"=="fast" set "PRESET_VALUES=!PRESET_fast!"
if /i "%QUALITY%"=="med" set "PRESET_VALUES=!PRESET_med!"
if /i "%QUALITY%"=="high" set "PRESET_VALUES=!PRESET_high!"
if /i "%QUALITY%"=="detailed" set "PRESET_VALUES=!PRESET_detailed!"
if /i "%QUALITY%"=="test" set "PRESET_VALUES=!PRESET_test!"
if /i "%QUALITY%"=="ark" set "PRESET_VALUES=!PRESET_ark!"

if "!PRESET_VALUES!"=="" (
    echo Error: Invalid quality setting '%QUALITY%'
    echo Valid options: fast, med, high, detailed, test, ark
    exit /b 1
)

echo Using %QUALITY% quality preset

REM Parse and assign parameters (space-delimited)
for /f "tokens=1-9" %%a in ("!PRESET_VALUES!") do (
    set AA=%%a
    set AB=%%b
    set AD=%%c
    set AS=%%d
    set AR=%%e
    set PS=%%f
    set PT=%%g
    set LR=%%h
    set LW=%%i
)

REM CUDA cache
set CUDA_CACHE_DISABLE=0
set CUDA_CACHE_MAXSIZE=1073741824
set CUDA_FORCE_PTX_JIT=1

REM Start batch timer
set BATCH_START_TIME=%TIME%
echo.
echo ========================================
if "%SINGLE_VIEW%"=="" (
    echo Starting batch render - ALL VIEWS
) else (
    echo Starting single view render
    echo View: %SINGLE_VIEW%
)
echo Octree: %OCTREE_NAME%
echo Quality: %QUALITY%
echo Resolution: %RES%px
echo ========================================
echo.

REM Determine view file pattern
if "%SINGLE_VIEW%"=="" (
    set VIEW_PATTERN=%VIEWS_DIR%\*.vp
) else (
    set VIEW_PATTERN=%VIEWS_DIR%\%SINGLE_VIEW%.vp
)

REM Count total views
set VIEW_COUNT=0
for %%f in (!VIEW_PATTERN!) do (
    set /a VIEW_COUNT+=1
)

if !VIEW_COUNT! EQU 0 (
    echo ERROR: No view files found matching pattern: !VIEW_PATTERN!
    exit /b 1
)

echo Found !VIEW_COUNT! view file^(s^) to render
echo.

REM Loop through view files
set CURRENT_VIEW=0
for %%f in (!VIEW_PATTERN!) do (
    set /a CURRENT_VIEW+=1
    set VIEW_PATH=%%f
    set VIEW_FULL_NAME=%%~nf
    call :RenderView
)
goto :AfterRenderView

:RenderView
    echo [!CURRENT_VIEW!/!VIEW_COUNT!] Processing view: !VIEW_FULL_NAME!

    REM Set file paths for this view
    set VIEW_FILE=!VIEW_PATH!

    REM Extract building/site and sky condition from octree name
    REM Format: {building}_with_site_{skyCondition}
    REM Split at "_with_site_" to get building and sky parts
    set "FULL_NAME=%OCTREE_NAME%"

    REM Replace _with_site_ with a delimiter, then split
    set "TEMP_NAME=!FULL_NAME:_with_site_=§!"
    for /f "tokens=1,2 delims=§" %%a in ("!TEMP_NAME!") do (
        set "BUILDING_PART=%%a"
        set "SKY_PART=%%b"
    )

    REM Construct new naming: building_with_site_view__skyCondition
    set AMB_FILE=outputs/images/!BUILDING_PART!_with_site_!VIEW_FULL_NAME!__!SKY_PART!.amb
    set OUTPUT_NAME=!BUILDING_PART!_with_site_!VIEW_FULL_NAME!__!SKY_PART!
    set OUTPUT_FILE=outputs/images/!OUTPUT_NAME!.hdr

    REM Start timer for this view
    set START_TIME=!TIME!
    echo   Rendering: !VIEW_FULL_NAME! ^> !OUTPUT_NAME!.hdr (!RES!px)
    echo   Start time: !START_TIME!

    REM Overture: Generate ambient file if it doesn't exist
    if exist "!AMB_FILE!" (
        echo   Overture: Using existing ambient file !AMB_FILE!
    ) else (
        echo   Overture: Generating ambient file !AMB_FILE!
        REM Use half AD and AS values for faster overture calculation
        set /a AD_OVERTURE=%AD%/2
        set /a AS_OVERTURE=%AS%/2
        accelerad_rpict -w+ -t 5 -vf "!VIEW_FILE!" -x 64 -y 64 -aa %AA% -ab %AB% -ad !AD_OVERTURE! -as !AS_OVERTURE! -ar %AR% -ps %PS% -pt %PT% -lr %LR% -lw %LW% -i -af "!AMB_FILE!" "%OCTREE%" > NUL
        set OVERTURE_ERROR=!errorlevel!
        if !OVERTURE_ERROR! neq 0 (
            echo   WARNING: Overture failed ^(exit code: !OVERTURE_ERROR!^), continuing with render anyway...
        )
    )

    REM Single-pass render using generated ambient file
    echo   Main render pass with ambient file...
    accelerad_rpict -w+ -t 5 -vf "!VIEW_FILE!" -x %RES% -y %RES% -aa %AA% -ab %AB% -ad %AD% -as %AS% -ar %AR% -ps %PS% -pt %PT% -lr %LR% -lw %LW% -i -af "!AMB_FILE!" "%OCTREE%" > "!OUTPUT_FILE!"
    set RENDER_ERROR=!errorlevel!
    if !RENDER_ERROR! neq 0 (
        echo   ERROR: Render failed for !VIEW_FULL_NAME! ^(exit code: !RENDER_ERROR!^)
        echo   Continuing with next view...
        echo.
    ) else (
        REM Apply pfilt noise reduction for high-resolution renders (4096+)
        if %RES% GEQ 4096 (
            echo   Applying pfilt noise reduction for high-resolution render...
            set DOWNSAMPLED_FILE=outputs/images/!OUTPUT_NAME!_filtered.hdr
            pfilt -x /2 -y /2 "!OUTPUT_FILE!" > "!DOWNSAMPLED_FILE!"
            if !errorlevel! neq 0 (
                echo   Warning: pfilt failed, keeping original render
            ) else (
                echo   Filtered output: !DOWNSAMPLED_FILE!
            )
        )

        REM Calculate elapsed time for this view
        set END_TIME=!TIME!

        REM Convert times to seconds for calculation (strip leading zeros to avoid octal interpretation)
        for /f "tokens=1-4 delims=:." %%a in ("!START_TIME!") do (
            set /a START_SEC=1%%a%%100*3600 + 1%%b%%100*60 + 1%%c%%100
        )
        for /f "tokens=1-4 delims=:." %%a in ("!END_TIME!") do (
            set /a END_SEC=1%%a%%100*3600 + 1%%b%%100*60 + 1%%c%%100
        )

        set /a ELAPSED_SEC=END_SEC-START_SEC
        if !ELAPSED_SEC! LSS 0 set /a ELAPSED_SEC+=86400

        set /a ELAPSED_MIN=ELAPSED_SEC/60
        set /a ELAPSED_SEC_REMAIN=ELAPSED_SEC%%60

        echo   Complete: !OUTPUT_FILE!
        echo   Time: !ELAPSED_MIN!m !ELAPSED_SEC_REMAIN!s
    )
    echo.
    exit /b 0

:AfterRenderView
REM Calculate total batch time
set BATCH_END_TIME=%TIME%

REM Convert times to seconds (strip leading zeros to avoid octal interpretation)
for /f "tokens=1-4 delims=:." %%a in ("%BATCH_START_TIME%") do (
    set /a BATCH_START_SEC=1%%a%%100*3600 + 1%%b%%100*60 + 1%%c%%100
)
for /f "tokens=1-4 delims=:." %%a in ("%BATCH_END_TIME%") do (
    set /a BATCH_END_SEC=1%%a%%100*3600 + 1%%b%%100*60 + 1%%c%%100
)

set /a BATCH_ELAPSED_SEC=BATCH_END_SEC-BATCH_START_SEC
if !BATCH_ELAPSED_SEC! LSS 0 set /a BATCH_ELAPSED_SEC+=86400

set /a BATCH_ELAPSED_MIN=BATCH_ELAPSED_SEC/60
set /a BATCH_ELAPSED_SEC_REMAIN=BATCH_ELAPSED_SEC%%60

echo ========================================
if "%SINGLE_VIEW%"=="" (
    echo Batch render complete
    echo Total views rendered: !VIEW_COUNT!
) else (
    echo Single view render complete
    echo View: %SINGLE_VIEW%
)
echo Total time: !BATCH_ELAPSED_MIN!m !BATCH_ELAPSED_SEC_REMAIN!s
echo ========================================
