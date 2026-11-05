@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo Creates a full ordinary ZIP in workspace\backups with a dated WorkThread-Full filename.
app\WorkThread.exe --workspace "%~dp0workspace" backup
if errorlevel 1 echo Backup failed; keep the existing backup files.
pause
