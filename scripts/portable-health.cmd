@echo off
cd /d "%~dp0"
app\WorkThread.exe --workspace "%~dp0workspace" doctor
pause
