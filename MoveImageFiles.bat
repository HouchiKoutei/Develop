@echo off
setlocal

REM ===== Destination folder =====
set DEST=D:\Files\all

if not exist "%DEST%" (
    mkdir "%DEST%"
)

echo =====================================
echo Starting file move process
echo =====================================

call :MOVE_FOLDER "C:\Users\houch\OneDrive"
call :MOVE_FOLDER "D:\Files\HispecPC"
call :MOVE_FOLDER "D:\Files\iPhone"
call :MOVE_FOLDER "D:\Files\SmartPhone01"
call :MOVE_FOLDER "D:\Files\SmartPhone02"
call :MOVE_FOLDER "D:\Files\SmartPhone03"

echo.
echo =====================================
echo Process Completed.
echo =====================================
pause
exit /b


:MOVE_FOLDER
if not exist "%~1" (
    echo [NOT FOUND] %~1
    exit /b
)

echo.
echo [SOURCE] %~1
echo -------------------------------------

REM /S    : Include subdirectories
REM /MOV  : Move files (delete from source after copy)
REM /R:0  : No retries on error (Skip immediately)
REM /W:0  : No wait time
REM /FP   : Show full path of files
REM /NDL  : Hide directory names (keep log clean)
REM /XX   : Hide "Extra Files" (already in destination)
REM /NC   : No Class (Hide "New File" labels for better readability)
REM /NFL  : Show file names
REM /NJH /NJS : Hide job header and summary
robocopy "%~1" "%DEST%" *.* /S /MOV /R:0 /W:0 /FP /NDL /XX /NC /NJH /NJS

exit /b