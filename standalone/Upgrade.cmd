@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0tool\WorkThreadUpgrade.exe" --release-dir "%~dp0release" %*
echo.
echo Exit code: %errorlevel%
echo Keep the logs folder. Read the result above before starting WorkThread.
pause
