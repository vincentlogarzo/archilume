@echo off
REM Usage: render.bat [VIEW_NAME] [OCTREE_NAME] [HIGHRES]
REM Example: render.bat plan_L08 22041_AR_T01_v2_with_site_TenK_cie_overcast 4096
REM Output will be: OCTREE_NAME__VIEW_NAME.hdr

REM Arguments
set VIEW_NAME=%1
set OCTREE_NAME=%2
set HIGHRES=%3

if "%VIEW_NAME%"=="" (
    echo Error: VIEW_NAME required
    echo Usage: render.bat [VIEW_NAME] [OCTREE_NAME] [HIGHRES]
    echo Example: render.bat plan_L08 22041_AR_T01_v2_with_site_TenK_cie_overcast 4096
    exit /b 1
)
if "%OCTREE_NAME%"=="" (
    echo Error: OCTREE_NAME required
    echo Usage: render.bat [VIEW_NAME] [OCTREE_NAME] [HIGHRES]
    echo Example: render.bat plan_L08 22041_AR_T01_v2_with_site_TenK_cie_overcast 4096
    exit /b 1
)

if "%HIGHRES%"=="" set HIGHRES=1024

REM Configuration
set VIEW_FILE=outputs/views_grids/%VIEW_NAME%.vp
set OCTREE=outputs/octree/%OCTREE_NAME%.oct
set AMB_FILE=outputs/images/%VIEW_NAME%.amb
set OUTPUT_NAME=%OCTREE_NAME%__%VIEW_NAME%
set OUTPUT_FILE=outputs/images/%OUTPUT_NAME%.hdr
set LOWRES=512

REM Quality parameters
set AA=0
set AB=1
set AD=2048
set AS=1024
set AR=128
set PS=1
set PT=0.02
set LR=12
set LW=0.0001

REM CUDA cache
set CUDA_CACHE_DISABLE=0
set CUDA_CACHE_MAXSIZE=1073741824
set CUDA_FORCE_PTX_JIT=1

echo Rendering: %VIEW_NAME% ^> %OUTPUT_NAME%.hdr (%LOWRES% then %HIGHRES%)

REM Pass 1: Build ambient cache
accelerad_rpict -w+ -t 1 -vf %VIEW_FILE% -x %LOWRES% -y %LOWRES% -aa %AA% -ab %AB% -ad %AD% -as %AS% -ar %AR% -ps %PS% -pt %PT% -lr %LR% -lw %LW% -i -af %AMB_FILE% %OCTREE% > NUL
if %errorlevel% neq 0 (
    echo Error in Pass 1
    exit /b 1
)

REM Pass 2: Final render
accelerad_rpict -w+ -t 1 -vf %VIEW_FILE% -x %HIGHRES% -y %HIGHRES% -aa %AA% -ab %AB% -ad %AD% -as %AS% -ar %AR% -ps %PS% -pt %PT% -lr %LR% -lw %LW% -i -af %AMB_FILE% %OCTREE% > %OUTPUT_FILE%
if %errorlevel% neq 0 (
    echo Error in Pass 2
    exit /b 1
)

echo Complete: %OUTPUT_FILE%
