@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "WT_RESTORE_SRC="
set "WT_RESTORE_DEST="
set /p "WT_RESTORE_SRC=ZIP backup file path (without surrounding quotes): "
if not defined WT_RESTORE_SRC exit /b 1
set /p "WT_RESTORE_DEST=New empty restore directory (without surrounding quotes): "
if not defined WT_RESTORE_DEST exit /b 1
if exist "%WT_RESTORE_DEST%" (
    echo Destination already exists. Choose a new directory; no files were changed.
    pause
    exit /b 1
)
call "%~dp0Run.cmd" --workspace "%WT_RESTORE_DEST%" restore "%WT_RESTORE_SRC%"
if errorlevel 1 goto failed
set "WT_RESTORE_CONFIRM="
set /p "WT_RESTORE_CONFIRM=Type RESTORE to apply the preview to this new directory: "
if not "%WT_RESTORE_CONFIRM%"=="RESTORE" exit /b 0
call "%~dp0Run.cmd" --workspace "%WT_RESTORE_DEST%" restore "%WT_RESTORE_SRC%" --apply
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo Restore failed. Existing source workspace and original backup are preserved.
pause
exit /b 1
