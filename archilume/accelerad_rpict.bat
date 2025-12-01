@echo off
setlocal enabledelayedexpansion

REM ============================================================================
REM Simplified Accelerad Batch Renderer
REM ============================================================================
REM Usage: accelerad_rpict_v2.bat OCTREE_NAME [QUALITY] [RES] [VIEW_NAME]
REM Example: ./archilume/accelerad_rpict.bat 87Cowles_BLD_withWindows_with_site_TenK_cie_overcast preview plan_ffl_090000

REM ============================================================================
REM 1. VALIDATE INPUTS
REM ============================================================================
if "%~1"=="" (
    echo ERROR: OCTREE_NAME required
    echo Usage: %~nx0 [OCTREE_NAME] [QUALITY] [VIEW_NAME]
    exit /b 1
)

set OCTREE_NAME=%~1
set QUALITY=%~2
set SINGLE_VIEW=%~3

REM Defaults
if "%QUALITY%"=="" set QUALITY=prev

REM --- 2. SETUP PATHS ---
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


REM when using .amb, same combination of ambient parameters for every rendering
REM that uses the ambient file. For susequent runs using an amb file 
REM you may reduce -ad and -as by < 50% + increase -aa by 0.05 or 0.1

set RES_OV=64
set AD_OV=2048
set AA_OV=0.01
set AB_OV=3
set AS_OV=1024
set AR_OV=1024
set /a LR_AMB=%AB_OV%+2

REM --- 3. QUALITY PRESETS ---           (RES    AA   AB      AD   AS   AR     PS  PT   LR       LW     DJ   DS   DT   DC   DR  DP  )

if /i "%QUALITY%"=="prev"       set PARAMS=256   0.01 %AB_OV% 2048 1024 %AR_OV% 4  0.15 %LR_AMB% 0.0010 0.0  0.25 0.50 0.25 0   512
if /i "%QUALITY%"=="draft"      set PARAMS=512   0.02 %AB_OV% 1792 1094 %AR_OV% 2  0.12 %LR_AMB% 0.0010 0.5  0.35 0.35 0.40 1   256
if /i "%QUALITY%"=="stand"      set PARAMS=1024  0.03 %AB_OV% 1536 718  %AR_OV% 2  0.10 %LR_AMB% 0.0010 0.7  0.50 0.25 0.50 1   256
if /i "%QUALITY%"=="prod"       set PARAMS=1536  0.03 %AB_OV% 1280 924  %AR_OV% 1  0.07 %LR_AMB% 0.0010 0.9  0.70 0.15 0.75 2   128
if /i "%QUALITY%"=="final"      set PARAMS=2048  0.03 %AB_OV% 1024 512  %AR_OV% 1  0.05 %LR_AMB% 0.0010 1.0  0.90 0.05 0.90 3   64
if /i "%QUALITY%"=="4K"         set PARAMS=4096  0.03 %AB_OV% 1024 512  %AR_OV% 1  0.05 %LR_AMB% 0.0010 1.0  0.90 0.05 0.90 3   64
if /i "%QUALITY%"=="custom"     set PARAMS=1024  0.01 8       4096 1024 1024    2  0.05 12       0.0001 0.7  0.50 0.25 0.50 1   256

if not defined PARAMS (
    echo ERROR: Invalid quality '%QUALITY%'
    echo Valid: prev, draft, stand, prod, final, 4K, custom
    exit /b 1
)

REM Parse parameters
for /f "tokens=1-16" %%a in ("%PARAMS%") do (
    set RES=%%a
    set AA=%%b
    set AB=%%c
    set AD=%%d
    set AS=%%e
    set AR=%%f
    set PS=%%g
    set PT=%%h
    set LR=%%i
    set LW=%%j
    set DJ=%%k
    set DS=%%l
    set DT=%%m
    set DC=%%n
    set DR=%%o
    set DP=%%p
)


REM --- 4. GPU CONFIGURATION ---
echo Checking for GPU...
nvidia-smi --query-gpu=memory.total --format=csv,nounits 2>nul | findstr /R "^[0-9]" > "%TEMP%\gpu_mem.txt" 2>nul
set /p GPU_VRAM_MB=<"%TEMP%\gpu_mem.txt" 2>nul
del "%TEMP%\gpu_mem.txt" 2>nul

if defined GPU_VRAM_MB (
    REM Verify it's a number by attempting arithmetic
    set /a "TEST=!GPU_VRAM_MB!+0" 2>nul
    if !errorlevel! neq 0 (
        echo WARNING: GPU detection returned invalid data, using defaults
        set CUDA_CACHE_MAXSIZE=1073741824
        set CUDA_CACHE_DISABLE=0
        set CUDA_FORCE_PTX_JIT=1
    ) else (
        set /a "GPU_VRAM_GB=!GPU_VRAM_MB!/1024"
        set /a "CACHE_MB=!GPU_VRAM_MB!*30/100"
        if !CACHE_MB! GTR 16384 set CACHE_MB=16384
        set /a "CUDA_CACHE_MAXSIZE=!CACHE_MB!*1024*1024"
        set CUDA_CACHE_DISABLE=0
        set CUDA_FORCE_PTX_JIT=1
        echo GPU: !GPU_VRAM_GB! GB ^(!GPU_VRAM_MB! MB^), Cache: !CACHE_MB! MB
    )
) else (
    echo WARNING: GPU not detected, using defaults
    set CUDA_CACHE_MAXSIZE=1073741824
    set CUDA_CACHE_DISABLE=0
    set CUDA_FORCE_PTX_JIT=1
)

REM --- 5. FIND VIEWS TO RENDER ---

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

REM --- 6. RENDER LOOP ---
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
goto :eof

REM --- SUBROUTINE: Render Single View --- 
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
    if exist "!HDR!" (echo   Skip: Output exists
        echo.
        exit /b 0
    )

    set START=%TIME%

    REM --- Overture (generate ambient file if missing) ---
    if not exist "!AMB!" (
        echo -------------------------------------------------------------------
        echo   Overture: Generating ambient file
        echo   ACCELERAD_EXE: %ACCELERAD_EXE%
        echo   OCTREE:        %OCTREE%
        echo   VIEW_FILE:     !VIEW_FILE! ^(%RES_OV%px^)
        echo   AMB_FILE:      !AMB!
        echo   COMMAND:       ""%ACCELERAD_EXE%" -w -t 1 -vf "!VIEW_FILE!" -x %RES_OV% -y %RES_OV% -aa %AA_OV% -ab %AB_OV% -ad %AD_OV% -as %AS_OV% -ar %AR_OV% -ps %PS% -pt %PT% -lr %LR% -lw %LW% -dj %DJ% -ds %DS% -dt %DT% -dc %DC% -dr %DR% -dp %DP% -i -af "!AMB!" "%OCTREE%">nul"
        echo -------------------------------------------------------------------
        "%ACCELERAD_EXE%" -w -t 1 -vf "!VIEW_FILE!" -x %RES_OV% -y %RES_OV% -aa %AA_OV% -ab %AB_OV% -ad %AD_OV% -as %AS_OV% -ar %AR_OV% -ps %PS% -pt %PT% -lr %LR% -lw %LW% -dj %DJ% -ds %DS% -dt %DT% -dc %DC% -dr %DR% -dp %DP% -i -af "!AMB!" "%OCTREE%">nul

        if !errorlevel! neq 0 echo   Warning: Overture failed, continuing...
        if not exist "!AMB!" echo   ERROR: Ambient file was not created!
    )

    REM --- Main render ---
    echo -------------------------------------------------------------------
    echo   Render:        !VIEW_NAME! in %RES%px
    echo   ACCELERAD_EXE: %ACCELERAD_EXE%
    echo   OCTREE:        %OCTREE%
    echo   VIEW_FILE:     !VIEW_FILE!
    echo   AMB_FILE:      !AMB!
    echo   HDR_FILE:      !HDR!
    echo   COMMAND:       ""%ACCELERAD_EXE%" -w -t 1 -vf "!VIEW_FILE!" -x %RES% -y %RES% -aa %AA% -ab %AB% -ad %AD% -as %AS% -ar %AR% -ps %PS% -pt %PT% -lr %LR% -lw %LW% -dj %DJ% -ds %DS% -dt %DT% -dc %DC% -dr %DR% -dp %DP% -i -af "!AMB!" "%OCTREE%" > "!HDR!""
    echo -------------------------------------------------------------------
    "%ACCELERAD_EXE%" -w -t 1 -vf "!VIEW_FILE!" -x %RES% -y %RES% -aa %AA% -ab %AB% -ad %AD% -as %AS% -ar %AR% -ps %PS% -pt %PT% -lr %LR% -lw %LW% -dj %DJ% -ds %DS% -dt %DT% -dc %DC% -dr %DR% -dp %DP% -i -af "!AMB!" "%OCTREE%" > "!HDR!"

    if !errorlevel! neq 0 (
        echo   ERROR: Render failed
    ) else (
        call :ElapsedTime "!START!" "!TIME!"
        echo   Complete: !ELAPSED!
    )
    echo.
    exit /b 0

REM --- SUBROUTINE: Calculate Elapsed Time ---
:ElapsedTime
    setlocal enabledelayedexpansion
    set T1=%~1
    set T2=%~2

    REM Parse start time - strip leading zeros to avoid octal interpretation
    for /f "tokens=1-3 delims=:." %%a in ("!T1!") do (
        set H1=%%a
        set M1=%%b
        set S1=%%c
    )
    REM Remove leading zeros
    set /a H1=1!H1!-100 2>nul || set H1=0
    set /a M1=1!M1!-100 2>nul || set M1=0
    set /a S1=1!S1!-100 2>nul || set S1=0
    set /a S1_TOTAL=H1*3600+M1*60+S1

    REM Parse end time
    for /f "tokens=1-3 delims=:." %%a in ("!T2!") do (
        set H2=%%a
        set M2=%%b
        set S2=%%c
    )
    REM Remove leading zeros
    set /a H2=1!H2!-100 2>nul || set H2=0
    set /a M2=1!M2!-100 2>nul || set M2=0
    set /a S2=1!S2!-100 2>nul || set S2=0
    set /a S2_TOTAL=H2*3600+M2*60+S2

    REM Calculate difference
    set /a DIFF=S2_TOTAL-S1_TOTAL
    if !DIFF! LSS 0 set /a DIFF+=86400

    set /a MIN=DIFF/60
    set /a SEC=DIFF-MIN*60
    set ELAPSED=!MIN!m !SEC!s
    endlocal & set ELAPSED=%ELAPSED%
    exit /b 0
