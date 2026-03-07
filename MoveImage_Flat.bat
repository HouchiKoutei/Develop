@echo on
setlocal EnableDelayedExpansion

REM ==========================
REM Settings
REM ==========================
set "ROOT=D:\Files\all"
set "LIST=%TEMP%\folders.txt"

echo =====================================
echo START MOVE PROCESS
echo ROOT = %ROOT%
echo =====================================

REM ==================================================
REM Phase 0: Remove EMPTY non-dot folders (PRE CLEAN)
REM ==================================================
echo === CLEAN EMPTY FOLDERS (PRE) ===

for /d %%D in ("%ROOT%\*") do call :CHECK_AND_CLEAN "%%D"

echo === CLEAN DONE ===

REM ==========================================
REM Build folder list (NON-DOT ONLY)
REM ==========================================
del "%LIST%" >nul 2>&1

for /d %%D in ("%ROOT%\*") do call :ADD_FOLDER "%%D"

REM ==========================================
REM Main Loop
REM ==========================================
:LOOP_START
if not exist "%LIST%" goto END

set /p SUB=<"%LIST%"
more +1 "%LIST%" > "%LIST%.tmp"
move /y "%LIST%.tmp" "%LIST%" >nul

echo -------------------------------------
echo PROCESSING: %SUB%

robocopy "%ROOT%\%SUB%" "%ROOT%" *.* /E /MOV /R:0 /W:0 >nul

if not exist "%ROOT%\%SUB%\*" (
    echo DELETE EMPTY: %ROOT%\%SUB%
    rmdir "%ROOT%\%SUB%"
) else (
    echo KEEP (not empty): %ROOT%\%SUB%
)

goto LOOP_START

REM ==========================================
REM Subroutines
REM ==========================================

:CHECK_AND_CLEAN
set "DIR=%~1"
set "NAME=%~nx1"

REM --- dot folder check (PIPE OK here) ---
echo %NAME% | findstr /b "." >nul
if not errorlevel 1 (
    echo SKIP DOT FOLDER (CLEAN): %DIR%
    goto :eof
)

REM --- empty folder check ---
if not exist "%DIR%\*" (
    echo REMOVE EMPTY FOLDER: %DIR%
    rmdir "%DIR%"
)
goto :eof


:ADD_FOLDER
set "NAME=%~nx1"
echo %NAME% | findstr /b "." >nul
if not errorlevel 1 goto :eof
echo %NAME%>>"%LIST%"
goto :eof

REM ==========================================
REM END
REM ==========================================
:END
del "%LIST%" >nul 2>&1
echo =====================================
echo DONE
echo =====================================
pause
