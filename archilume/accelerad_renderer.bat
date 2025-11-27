@echo off
setlocal enabledelayedexpansion
REM Usage: render.bat [VIEW_NAME] [OCTREE_NAME] [QUALITY] [HIGHRES]
REM Example: render.bat plan_L08 22041_AR_T01_v2_with_site_TenK_cie_overcast detailed 2048
REM Quality options: fast, medium, detailed, ultra

REM Arguments
set VIEW_NAME=%1
set OCTREE_NAME=%2
set QUALITY=%3
set HIGHRES=%4

if "%VIEW_NAME%"=="" (
    echo Error: VIEW_NAME required
    echo Usage: render.bat [VIEW_NAME] [OCTREE_NAME] [QUALITY] [HIGHRES]
    echo Quality options: fast, medium, detailed, ultra
    echo Example: render.bat plan_L08 22041_AR_T01_v2_with_site_TenK_cie_overcast detailed 2048
    exit /b 1
)
if "%OCTREE_NAME%"=="" (
    echo Error: OCTREE_NAME required
    echo Usage: render.bat [VIEW_NAME] [OCTREE_NAME] [QUALITY] [HIGHRES]
    echo Quality options: fast, medium, detailed, ultra
    echo Example: render.bat plan_L08 22041_AR_T01_v2_with_site_TenK_cie_overcast detailed 2048
    exit /b 1
)

REM Set default quality and resolution
if "%QUALITY%"=="" set QUALITY=fast
if "%HIGHRES%"=="" set HIGHRES=1024

REM Configuration
set VIEW_FILE=outputs/views_grids/%VIEW_NAME%.vp
set OCTREE=outputs/octree/%OCTREE_NAME%.oct
set AMB_FILE=outputs/images/%VIEW_NAME%.amb
set OUTPUT_NAME=%OCTREE_NAME%__%VIEW_NAME%_%QUALITY%
set OUTPUT_FILE=outputs/images/%OUTPUT_NAME%.hdr

REM Quality preset selection
if /i "%QUALITY%"=="fast" (
    echo Using FAST quality preset
    set AA=0.05
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
) else (
    echo Error: Invalid quality setting '%QUALITY%'
    echo Valid options: fast, medium, detailed, ultra
    exit /b 1
)

REM CUDA cache
set CUDA_CACHE_DISABLE=0
set CUDA_CACHE_MAXSIZE=1073741824
set CUDA_FORCE_PTX_JIT=1

REM Start timer
set START_TIME=%TIME%
echo Rendering: %VIEW_NAME% ^> %OUTPUT_NAME%.hdr (%HIGHRES%px)
echo Start time: %START_TIME%

REM Single-pass render
accelerad_rpict -w+ -t 1 -vf %VIEW_FILE% -x %HIGHRES% -y %HIGHRES% -aa %AA% -ab %AB% -ad %AD% -as %AS% -ar %AR% -ps %PS% -pt %PT% -lr %LR% -lw %LW% -i %OCTREE% > %OUTPUT_FILE%
if %errorlevel% neq 0 (
    echo Error in render
    exit /b 1
)

REM Apply pfilt noise reduction for high-resolution renders (4096+)
if %HIGHRES% GEQ 4096 (
    echo Applying pfilt noise reduction for high-resolution render...
    set DOWNSAMPLED_FILE=outputs/images/%OUTPUT_NAME%_filtered.hdr
    pfilt -x /2 -y /2 %OUTPUT_FILE% > !DOWNSAMPLED_FILE!
    if !errorlevel! neq 0 (
        echo Warning: pfilt failed, keeping original render
    ) else (
        echo Filtered output: !DOWNSAMPLED_FILE!
    )
)

REM Calculate elapsed time
set END_TIME=%TIME%

REM Convert times to seconds for calculation
for /f "tokens=1-4 delims=:." %%a in ("%START_TIME%") do (
    set /a START_SEC=%%a*3600 + %%b*60 + %%c
)
for /f "tokens=1-4 delims=:." %%a in ("%END_TIME%") do (
    set /a END_SEC=%%a*3600 + %%b*60 + %%c
)

set /a ELAPSED_SEC=END_SEC-START_SEC
if %ELAPSED_SEC% LSS 0 set /a ELAPSED_SEC+=86400

set /a ELAPSED_MIN=ELAPSED_SEC/60
set /a ELAPSED_SEC_REMAIN=ELAPSED_SEC%%60

echo.
echo Complete: %OUTPUT_FILE%
echo Total time: %ELAPSED_MIN%m %ELAPSED_SEC_REMAIN%s