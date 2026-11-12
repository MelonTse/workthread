@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0tool\WorkThreadUpgrade.exe" --release-dir "%~dp0release" %*
set "tool_exit=%errorlevel%"
echo.
echo TOOL EXIT CODE: %tool_exit%
echo Keep the logs folder. Read the result above before starting WorkThread.
echo Pressing a key only closes this window; it does NOT mean the upgrade succeeded.
pause
exit /b %tool_exit%
