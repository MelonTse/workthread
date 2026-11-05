@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
app\WorkThread.exe --workspace "%~dp0workspace" init
if errorlevel 1 goto failed
app\WorkThread.exe --workspace "%~dp0acceptance" init
if errorlevel 1 goto failed
app\WorkThread.exe --workspace "%~dp0workspace" doctor
if errorlevel 1 goto failed
app\WorkThread.exe --workspace "%~dp0acceptance" doctor
if errorlevel 1 goto failed
echo Both independent workspaces initialized. Start with Start.cmd.
pause
exit /b 0
:failed
echo Initialization failed or custom template conflicts need attention. Existing data is preserved.
pause
exit /b 1
