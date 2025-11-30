@echo off
rem This batch script tests that accelerad_rtrace runs.
accelerad_rcontrib -version
if errorlevel 1 goto FAILURE
set out=test_rcontrib.txt
if exist %out% del %out%
accelerad_rcontrib -h -lr 8 -lw .002 -x 5 -y 5 -m sky_mat test.oct < test.inp > %out%
if errorlevel 1 goto FAILURE
if not exist %out% goto FAILURE
for %%a in (%out%) do set length=%%~za
if %length%==0 goto FAILURE
echo Accelerad rcontrib succeeded!
goto END
:FAILURE
echo Accelerad rcontrib failed
:END
pause