@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0Run.cmd" --workspace "%~dp0workspace" doctor
pause
