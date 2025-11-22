@echo off

REM バッチファイルが存在するディレクトリを格納
set SCRIPT_DIR=%~dp0

NET SESSION >nul 2>&1

echo [INFO] Running PowerShell script with temporary policy override...

REM 絶対パスを使用して PowerShell スクリプトを実行
PowerShell.exe -ExecutionPolicy Bypass -File "%SCRIPT_DIR%dify.ps1"

echo [INFO] PowerShell script finished.
pause