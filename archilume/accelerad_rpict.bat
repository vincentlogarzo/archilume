@echo off
setlocal enabledelayedexpansion

REM ============================================================================
REM Simplified Accelerad Batch Renderer
REM ============================================================================
REM Usage: accelerad_rpict_v2.bat OCTREE_NAME [QUALITY] [RES] [VIEW_NAME]
REM Example: ./archilume/accelerad_rpict.bat 87Cowles_BLD_withWindows_with_site_TenK_cie_overcast fast 512 plan_ffl_090000

REM ============================================================================
REM 1. VALIDATE INPUTS
REM ============================================================================
if "%~1"=="" (
    echo ERROR: OCTREE_NAME required
    echo Usage: %~nx0 OCTREE_NAME [QUALITY] [RES] [VIEW_NAME]
    exit /b 1
)

set OCTREE_NAME=%~1
set QUALITY=%~2
set RES=%~3
set SINGLE_VIEW=%~4

REM Defaults
if "%QUALITY%"=="" set QUALITY=fast
if "%RES%"=="" set RES=1024

REM ============================================================================
REM 2. SETUP PATHS
REM ============================================================================
set ACCELERAD_EXE=%~dp0../.devcontainer/accelerad_07_beta_Windows/bin/accelerad_rpict.exe
set OCTREE=outputs/octree/%OCTREE_NAME%.oct
set VIEW_DIR=outputs/view
set IMAGE_DIR=outputs/image

if not exist "%ACCELERAD_EXE%" (
    echo ERROR: Accelerad not found at %ACCELERAD_EXE%
    exit /b 1
)

if not exist "%OCTREE%" (
    echo ERROR: Octree not found at %OCTREE%
    exit /b 1
)

REM ============================================================================
REM 3. QUALITY PRESETS                  (AA   AB AD  AS   AR   PS PT  LR LW)
REM ============================================================================
if /i "%QUALITY%"=="fast"     set PARAMS=0.07 3 1024 0256 0124 2 0.10 12 0.0010
if /i "%QUALITY%"=="med"      set PARAMS=0.05 3 1024 0256 0512 2 0.10 12 0.0010
if /i "%QUALITY%"=="high"     set PARAMS=0.02 3 1024 0512 0512 2 0.10 12 0.0010
if /i "%QUALITY%"=="detailed" set PARAMS=0.01 1 2048 1024 1024 1 0.02 12 0.0001
if /i "%QUALITY%"=="test"     set PARAMS=0.01 8 4096 1024 1024 2 0.05 12 0.0001
if /i "%QUALITY%"=="ark"      set PARAMS=0.01 8 4096 1024 1024 4 0.05 12 0.0002

if not defined PARAMS (
    echo ERROR: Invalid quality '%QUALITY%'
    echo Valid: fast, med, high, detailed, test, ark
    exit /b 1
)

REM Parse parameters
for /f "tokens=1-9" %%a in ("%PARAMS%") do (
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

REM ============================================================================
REM 4. GPU CONFIGURATION
REM ============================================================================
for /f "skip=1 tokens=*" %%i in ('nvidia-smi --query-gpu=memory.total --format=csv,nounits 2^>nul') do set GPU_VRAM_MB=%%i

if defined GPU_VRAM_MB (
    set /a GPU_VRAM_GB=GPU_VRAM_MB/1024
    set /a CACHE_MB=GPU_VRAM_MB*30/100
    if !CACHE_MB! GTR 16384 set CACHE_MB=16384
    set /a CUDA_CACHE_MAXSIZE=CACHE_MB*1024*1024
    set CUDA_CACHE_DISABLE=0
    set CUDA_FORCE_PTX_JIT=1
    echo GPU: !GPU_VRAM_GB! GB, Cache: !CACHE_MB! MB
) else (
    echo WARNING: GPU not detected, using defaults
    set CUDA_CACHE_MAXSIZE=1073741824
    set CUDA_CACHE_DISABLE=0
    set CUDA_FORCE_PTX_JIT=1
)

REM ============================================================================
REM 5. FIND VIEWS TO RENDER
REM ============================================================================
if "%SINGLE_VIEW%"=="" (
    echo Mode: Batch render ALL views
    set VIEW_COUNT=0
    for %%f in ("%VIEW_DIR%\*.vp") do set /a VIEW_COUNT+=1
) else (
    echo Mode: Single view '%SINGLE_VIEW%'
    set VIEW_COUNT=1
    if not exist "%VIEW_DIR%\%SINGLE_VIEW%.vp" (
        echo ERROR: View file not found: %VIEW_DIR%\%SINGLE_VIEW%.vp
        exit /b 1
    )
)

if !VIEW_COUNT! EQU 0 (
    echo ERROR: No view files found in %VIEW_DIR%
    exit /b 1
)

echo Found !VIEW_COUNT! view(s), Quality: %QUALITY%, Resolution: %RES%px
echo.

REM ============================================================================
REM 6. RENDER LOOP
REM ============================================================================
set BATCH_START=%TIME%
set CURRENT=0

REM Determine search pattern based on single view or all views
if "%SINGLE_VIEW%"=="" (
    REM Render all views - use wildcard
    for %%f in ("%VIEW_DIR%\*.vp") do (
        set /a CURRENT+=1
        set TEMP_VIEW_FILE=%%f
        set TEMP_VIEW_NAME=%%~nxf
        call :RenderOne
    )
) else (
    REM Render single view - use specific file
    set /a CURRENT+=1
    set TEMP_VIEW_FILE=%VIEW_DIR%\%SINGLE_VIEW%.vp
    for %%f in ("%VIEW_DIR%\%SINGLE_VIEW%.vp") do set TEMP_VIEW_NAME=%%~nxf
    call :RenderOne
)

REM Calculate total time
call :ElapsedTime "%BATCH_START%" "%TIME%"
echo.
echo ============================================================================
echo Batch complete: !VIEW_COUNT! views in !ELAPSED!
echo ============================================================================
exit /b 0

REM ============================================================================
REM SUBROUTINE: Render Single View
REM ============================================================================
:RenderOne
    REM TEMP_VIEW_FILE contains the full path from the wildcard
    set VIEW_FILE=!TEMP_VIEW_FILE!
    set VIEW_NAME=!TEMP_VIEW_NAME!
    set VIEW_NAME=!VIEW_NAME:~0,-3!

    echo [!CURRENT!/!VIEW_COUNT!] %VIEW_NAME%

    REM Parse octree name: building_with_site_skyCondition
    set FULL=%OCTREE_NAME%
    set TEMP=!FULL:_with_site_=§!
    for /f "tokens=1,2 delims=§" %%a in ("!TEMP!") do (
        set BUILDING=%%a
        set SKY=%%b
    )

    REM Output paths
    set AMB=%IMAGE_DIR%/!BUILDING!_with_site_!VIEW_NAME!__!SKY!.amb
    set HDR=%IMAGE_DIR%/!BUILDING!_with_site_!VIEW_NAME!__!SKY!.hdr

    REM Skip if already exists
    if exist "!HDR!" (
        echo   Skip: Output exists
        echo.
        exit /b 0
    )

    set START=%TIME%

    REM Overture (generate ambient file if missing)
    if not exist "!AMB!" (
        echo   Overture: Generating ambient file
        set /a AD_HALF=AD/2
        set /a AS_HALF=AS/2
        "%ACCELERAD_EXE%" -w+ -t 5 -vf "!VIEW_FILE!" -x 64 -y 64 ^
            -aa %AA% -ab %AB% -ad !AD_HALF! -as !AS_HALF! -ar %AR% ^
            -ps %PS% -pt %PT% -lr %LR% -lw %LW% -i -af "!AMB!" "%OCTREE%" >nul 2>&1
        if !errorlevel! neq 0 echo   Warning: Overture failed, continuing...
    ) else (
        echo   Overture: Using existing ambient
    )

    REM Main render
    echo   Render: !VIEW_NAME! ^> %RES%px
    "%ACCELERAD_EXE%" -w+ -t 5 -vf "!VIEW_FILE!" -x %RES% -y %RES% ^
        -aa %AA% -ab %AB% -ad %AD% -as %AS% -ar %AR% ^
        -ps %PS% -pt %PT% -lr %LR% -lw %LW% -i -af "!AMB!" "%OCTREE%" > "!HDR!"

    if !errorlevel! neq 0 (
        echo   ERROR: Render failed
    ) else (
        call :ElapsedTime "!START!" "!TIME!"
        echo   Complete: !ELAPSED!
    )
    echo.
    exit /b 0

REM ============================================================================
REM SUBROUTINE: Calculate Elapsed Time
REM ============================================================================
:ElapsedTime
    set T1=%~1
    set T2=%~2

    REM Parse start time
    for /f "tokens=1-4 delims=:." %%a in ("%T1%") do (
        set /a S1=1%%a%%100*3600 + 1%%b%%100*60 + 1%%c%%100 2>nul
    )

    REM Parse end time
    for /f "tokens=1-4 delims=:." %%a in ("%T2%") do (
        set /a S2=1%%a%%100*3600 + 1%%b%%100*60 + 1%%c%%100 2>nul
    )

    REM Calculate difference
    set /a DIFF=S2-S1
    if !DIFF! LSS 0 set /a DIFF+=86400

    set /a MIN=DIFF/60
    set /a SEC=DIFF%%60
    set ELAPSED=!MIN!m !SEC!s
    exit /b 0
