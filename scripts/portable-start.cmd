@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0Run.cmd" --workspace "%~dp0workspace" serve --open
set "workthread_exit=%errorlevel%"
if not "%workthread_exit%"=="0" pause
exit /b %workthread_exit%
