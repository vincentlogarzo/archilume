@echo off
setlocal enabledelayedexpansion

echo ============================================================================
echo DIAGNOSTIC TEST FOR ACCELERAD_RPICT.BAT
echo ============================================================================
echo.

REM Test parameters
set OCTREE_NAME=87Cowles_BLD_withWindows_with_site_TenK_cie_overcast
set QUALITY=fast
set RES=2048
set SINGLE_VIEW=plan_ffl_090000
set VIEW_DIR=outputs/view

echo [TEST 1] Parameters
echo   OCTREE_NAME: %OCTREE_NAME%
echo   QUALITY: %QUALITY%
echo   RES: %RES%
echo   SINGLE_VIEW: %SINGLE_VIEW%
echo.

echo [TEST 2] Quality preset parsing
set "PRESET_fast=0.07 3 1024 256 124 2 0.1 3 0.001"
for /f "tokens=1-9" %%a in ("!PRESET_fast!") do (
    set "AA=%%a"
    set "AB=%%b"
    set "AD=%%c"
    set "AS=%%d"
)
echo   AA=%AA%, AB=%AB%, AD=%AD%, AS=%AS%
echo.

echo [TEST 3] Space trimming
set AD=%AD: =%
set AS=%AS: =%
echo   Trimmed AD=%AD%, AS=%AS%
echo.

echo [TEST 4] Arithmetic operations
set /a AD_OVERTURE=%AD%/2
set /a AS_OVERTURE=%AS%/2
echo   AD_OVERTURE=%AD_OVERTURE%, AS_OVERTURE=%AS_OVERTURE%
if %ERRORLEVEL% NEQ 0 (
    echo   ERROR: Arithmetic failed!
    exit /b 1
)
echo   OK: Arithmetic passed
echo.

echo [TEST 5] View pattern generation
if "%SINGLE_VIEW%"=="" (
    set VIEW_PATTERN=%VIEW_DIR%/*.vp
) else (
    set VIEW_PATTERN=%VIEW_DIR%/%SINGLE_VIEW%.vp
)
echo   VIEW_PATTERN: !VIEW_PATTERN!
echo.

echo [TEST 6] View file count
set VIEW_COUNT=0
for %%f in (!VIEW_PATTERN!) do (
    set /a VIEW_COUNT+=1
    echo   Found: %%f
)
echo   Total VIEW_COUNT: !VIEW_COUNT!
if !VIEW_COUNT! EQU 0 (
    echo   ERROR: No view files found!
    exit /b 1
)
echo   OK: View files found
echo.

echo [TEST 7] Accelerad executable path
set "ACCELERAD_PATH=.devcontainer\accelerad_07_beta_Windows\bin\accelerad_rpict.exe"
if exist "!ACCELERAD_PATH!" (
    echo   OK: Found accelerad_rpict.exe
) else (
    echo   ERROR: Accelerad executable not found at: !ACCELERAD_PATH!
    exit /b 1
)
echo.

echo ============================================================================
echo ALL TESTS PASSED!
echo ============================================================================
pause
