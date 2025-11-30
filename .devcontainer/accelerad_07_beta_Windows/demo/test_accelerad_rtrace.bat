@echo off
rem This batch script tests that accelerad_rtrace runs.
accelerad_rtrace -version
if errorlevel 1 goto FAILURE
set out=test_rtrace.txt
if exist %out% del %out%
accelerad_rtrace -h -aa 0 -ad 1024 -as 0 -lr 8 -lw .002 -x 5 -y 5 -ovodwl test.oct < test.inp > %out%
if errorlevel 1 goto FAILURE
if not exist %out% goto FAILURE
for %%a in (%out%) do set length=%%~za
if %length%==0 goto FAILURE
echo Accelerad rtrace succeeded!
goto END
:FAILURE
echo Accelerad rtrace failed
:END
pause