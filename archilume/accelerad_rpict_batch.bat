@echo off
setlocal enabledelayedexpansion
REM Usage: accelerad_renderer_batch.bat [OCTREE_NAME] [QUALITY] [RES] [VIEW_NAME]
REM Example (all views): accelerad_renderer_batch.bat octree detailed 2048
REM Example (single view): accelerad_renderer_batch.bat octree detailed 2048 plan_L01
REM If VIEW_NAME is omitted, ALL view files in outputs/views_grids/ will be rendered
REM Quality options: fast, medium, high, detailed, test, ark

REM Arguments
set OCTREE_NAME=%1
set QUALITY=%2
set RES=%3
set SINGLE_VIEW=%4

if "%OCTREE_NAME%"=="" (
    echo Error: OCTREE_NAME required
    echo Usage: accelerad_renderer_batch.bat [OCTREE_NAME] [QUALITY] [RES] [VIEW_NAME]
    echo Quality options: fast, medium, high, detailed, test, ark
    echo Example all views: accelerad_renderer_batch.bat 87Cowles_BLD_withWindows_with_site_TenK_cie_overcast detailed 2048
    echo Example single view: accelerad_renderer_batch.bat 87Cowles_BLD_withWindows_with_site_TenK_cie_overcast detailed 2048 plan_L01
    exit /b 1
)

REM Set default quality and resolution
if "%QUALITY%"=="" set QUALITY=fast
if "%RES%"=="" set RES=1024

REM Configuration
set OCTREE=outputs/octree/%OCTREE_NAME%.oct
set VIEWS_DIR=outputs/views_grids

REM Quality preset selection
if /i "%QUALITY%"=="fast" (
    echo Using FAST quality preset
    set AA=0.2
    set AB=3
    set AD=512
    set AS=256
    set AR=128
    set PS=4
    set PT=0.12
    set LR=12
    set LW=0.002
) else if /i "%QUALITY%"=="medium" (
    echo Using MEDIUM quality preset
    set AA=0.05
    set AB=3
    set AD=1024
    set AS=256
    set AR=128
    set PS=4
    set PT=0.1
    set LR=12
    set LW=0.001
) else if /i "%QUALITY%"=="high" (
    echo Using HIGH quality preset
    set AA=0.05
    set AB=3
    set AD=1024
    set AS=256
    set AR=128
    set PS=2
    set PT=0.1
    set LR=12
    set LW=0.001
) else if /i "%QUALITY%"=="detailed" (
    echo Using DETAILED quality preset
    set AA=0
    set AB=1
    set AD=2048
    set AS=1024
    set AR=128
    set PS=1
    set PT=0.02
    set LR=12
    set LW=0.0001
) else if /i "%QUALITY%"=="test" (
    echo Using TEST quality preset
    set AA=0.05
    set AB=8
    set AD=1024
    set AS=256
    set AR=512
    set PS=2
    set PT=0.12
    set LR=12
    set LW=0.0005
) else if /i "%QUALITY%"=="ark" (
    echo Using ARK quality preset
    set AA=0.01
    set AB=8
    set AD=4096
    set AS=1024
    set AR=1024
    set PS=4
    set PT=0.05
    set LR=16
    set LW=0.0002
) else (
    echo Error: Invalid quality setting '%QUALITY%'
    echo Valid options: fast, medium, high, detailed, test, ark
    exit /b 1
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
    set OUTPUT_NAME=!BUILDING_PART!_with_site_!VIEW_FULL_NAME!__!SKY_PART!_%QUALITY%
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
        accelerad_rpict -w+ -t 1 -vf "!VIEW_FILE!" -x 64 -y 64 -aa %AA% -ab %AB% -ad %AD% -as %AS% -ar %AR% -ps %PS% -pt %PT% -lr %LR% -lw %LW% -i -af "!AMB_FILE!" "%OCTREE%" > NUL
        set OVERTURE_ERROR=!errorlevel!
        if !OVERTURE_ERROR! neq 0 (
            echo   WARNING: Overture failed ^(exit code: !OVERTURE_ERROR!^), continuing with render anyway...
        )
    )

    REM Single-pass render using generated ambient file
    echo   Main render pass with ambient file...
    accelerad_rpict -w+ -t 1 -vf "!VIEW_FILE!" -x %RES% -y %RES% -aa %AA% -ab %AB% -ad %AD% -as %AS% -ar %AR% -ps %PS% -pt %PT% -lr %LR% -lw %LW% -i -af "!AMB_FILE!" "%OCTREE%" > "!OUTPUT_FILE!"
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

        REM Convert times to seconds for calculation
        for /f "tokens=1-4 delims=:." %%a in ("!START_TIME!") do (
            set /a START_SEC=%%a*3600 + %%b*60 + %%c
        )
        for /f "tokens=1-4 delims=:." %%a in ("!END_TIME!") do (
            set /a END_SEC=%%a*3600 + %%b*60 + %%c
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

for /f "tokens=1-4 delims=:." %%a in ("%BATCH_START_TIME%") do (
    set /a BATCH_START_SEC=%%a*3600 + %%b*60 + %%c
)
for /f "tokens=1-4 delims=:." %%a in ("%BATCH_END_TIME%") do (
    set /a BATCH_END_SEC=%%a*3600 + %%b*60 + %%c
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
