@echo off
cd /d "%~dp0"
set /p "WT_RESTORE_SRC=Backup file path (.7z): "
app\WorkThread.exe --workspace "%~dp0workspace" restore "%WT_RESTORE_SRC%"
set /p "WT_RESTORE_CONFIRM=Type RESTORE to replace workspace (keeps rollback copy): "
if "%WT_RESTORE_CONFIRM%"=="RESTORE" app\WorkThread.exe --workspace "%~dp0workspace" restore "%WT_RESTORE_SRC%" --apply
pause
