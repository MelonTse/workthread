@echo off
cd /d "%~dp0"
set /p "WT_BACKUP_DEST=Backup output path (.7z): "
app\WorkThread.exe --workspace "%~dp0workspace" backup "%WT_BACKUP_DEST%"
pause
