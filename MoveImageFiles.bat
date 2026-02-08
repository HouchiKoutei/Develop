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

call :MOVE_FOLDER C:\Users\houch\OneDrive
call :MOVE_FOLDER D:\Files\HispecPC
call :MOVE_FOLDER D:\Files\iPhone
call :MOVE_FOLDER D:\Files\SmartPhone01
call :MOVE_FOLDER D:\Files\SmartPhone02
call :MOVE_FOLDER D:\Files\SmartPhone03

echo.
echo =====================================
echo Done.
echo =====================================
pause
exit /b


:MOVE_FOLDER
if not exist "%~1" (
    echo Folder not found: %~1
    exit /b
)

echo Processing folder: %~1

REM Move all files from subfolders to DEST (flat)
robocopy "%~1" "%DEST%" *.* /S /MOV >nul

exit /b
