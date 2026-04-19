@echo off
REM Archilume launcher (Windows double-click entry point).
REM
REM Invokes launch-archilume.ps1 with an explicit execution policy bypass so
REM the script runs regardless of the host's PowerShell ExecutionPolicy or any
REM mark-of-the-web attribute left by unzipping. `pause` keeps the window open
REM on exit so users can read output and any error messages.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch-archilume.ps1"
echo.
pause