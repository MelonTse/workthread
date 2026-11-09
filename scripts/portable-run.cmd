@echo off
setlocal
set "helper=%~dp0.workthread-updates\bootstrap\WorkThread.exe"
if not exist "%helper%" set "helper=%~dp0app\WorkThread.exe"
"%helper%" --maintenance launch "%~dp0." %*
exit /b %errorlevel%
