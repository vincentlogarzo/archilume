@echo off
rem This batch script tests that accelerad_rpict runs.
accelerad_rpict -version
if errorlevel 1 goto FAILURE
set out=test_rpict.hdr
if exist %out% del %out%
accelerad_rpict -vp 10.0 -2.0 1.5 -vd -1.0 0.0 0.0 -vu 0 0 1 -ab 2 -aa .18 -ad 1024 -as 0 -lr 8 -lw .002 -x 512 -y 512 -pj 0 -ac 1024 test.oct > %out%
if errorlevel 1 goto FAILURE
if not exist %out% goto FAILURE
for %%a in (%out%) do set length=%%~za
if %length%==0 goto FAILURE
echo Accelerad rpict succeeded!
goto END
:FAILURE
echo Accelerad rpict failed
:END
pause