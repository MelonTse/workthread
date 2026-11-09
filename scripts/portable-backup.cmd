@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo Creates a full ordinary ZIP in workspace\backups with a dated WorkThread-Full filename.
call "%~dp0Run.cmd" --workspace "%~dp0workspace" backup
if errorlevel 1 echo Backup failed; keep the existing backup files.
pause
