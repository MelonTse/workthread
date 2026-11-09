@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0Run.cmd" --workspace "%~dp0workspace" init
if errorlevel 1 goto failed
call "%~dp0Run.cmd" --workspace "%~dp0acceptance" init
if errorlevel 1 goto failed
call "%~dp0Run.cmd" --workspace "%~dp0workspace" doctor
if errorlevel 1 goto failed
call "%~dp0Run.cmd" --workspace "%~dp0acceptance" doctor
if errorlevel 1 goto failed
echo Both independent workspaces initialized. Start with Start.cmd.
if /I not "%~1"=="/quiet" pause
exit /b 0
:failed
echo Initialization failed or custom template conflicts need attention. Existing data is preserved.
if /I not "%~1"=="/quiet" pause
exit /b 1
