@echo off
REM -------------------------------------------
REM USB Portable Git + SSH Setup for VSCode + GitHub Test (GitHubサイト自動オープン追加版)
REM -------------------------------------------

REM 1. ユーザー設定
SET USER_NAME=houchikoutei
SET USER_EMAIL=houchikoutei@gmail.com

REM 2. 実行ドライブを取得
SET ROOT_DRIVE=%~d0

REM 3. パス定義
SET GIT_DIR=%ROOT_DRIVE%\ProgramFiles\Coding\PortableGit
SET SSH_DIR=%GIT_DIR%\usr\bin
SET KEY_DIR=%GIT_DIR%\ssh_keys
SET KEY_FILE=%KEY_DIR%\id_rsa_%USER_NAME%
SET GIT_CMD=%GIT_DIR%\cmd\git.exe
SET VSCODE_DIR=%ROOT_DRIVE%\ProgramFiles\Coding\VSCode-win32-x64-1.105.0-insider
SET VSCODE_SETTINGS=%VSCODE_DIR%\data\user-data\User\settings.json
REM ユーザー名の付いた設定ファイルを定義
SET PORTABLE_GITCONFIG=%GIT_DIR%\portable_gitconfig_%USER_NAME%
SET PYTHON_PATH=%ROOT_DRIVE%\ProgramFiles\Coding\WPy64-38100\python-3.8.10.amd64\python.exe

REM 4. パス確認
if not exist "%GIT_CMD%" (
    echo ERROR: Git not found at %GIT_CMD%
    pause
    exit /b
)
if not exist "%SSH_DIR%\ssh-keygen.exe" (
    echo ERROR: ssh-keygen.exe not found at %SSH_DIR%\ssh-keygen.exe
    pause
    exit /b
)

REM 5. SSHキー作成 (キーファイル名にユーザー名を追加し、切り替えに対応)
if not exist "%KEY_DIR%" mkdir "%KEY_DIR%"
if not exist "%KEY_FILE%" (
    echo Generating SSH key...
    "%SSH_DIR%\ssh-keygen.exe" -t rsa -b 4096 -f "%KEY_FILE%" -C "%USER_EMAIL%" -N ""
) else (
    echo SSH key already exists.
)

REM 6. SSHエージェントのクリアと鍵のロード
echo Removing old SSH identities and loading new key...

REM 実行中の SSH Agent があれば停止/クリアを試みる
"%SSH_DIR%\ssh-add.exe" -D >nul 2>&1
"%SSH_DIR%\ssh-add.exe" -k >nul 2>&1

REM 作成した秘密鍵をSSHエージェントにロード
"%SSH_DIR%\ssh-add.exe" "%KEY_FILE%" >nul 2>&1

REM 7. ユーザー設定ファイルを作成し、環境変数で指定
echo [user] > "%PORTABLE_GITCONFIG%"
echo     name = %USER_NAME% >> "%PORTABLE_GITCONFIG%"
echo     email = %USER_EMAIL% >> "%PORTABLE_GITCONFIG%"
echo [core] >> "%PORTABLE_GITCONFIG%"
echo     sshCommand = "\"%SSH_DIR%\ssh.exe\" -i \"%KEY_FILE%\"" >> "%PORTABLE_GITCONFIG%"

echo Applying portable config file: %PORTABLE_GITCONFIG%
SET GIT_CONFIG_GLOBAL=%PORTABLE_GITCONFIG%

REM 8. VSCode 設定更新
if not exist "%VSCODE_DIR%\data\user-data\User" mkdir "%VSCODE_DIR%\data\user-data\User"

powershell -NoProfile -ExecutionPolicy Bypass ^
  "$settings = '%VSCODE_SETTINGS%';" ^
  "if (!(Test-Path $settings)) { '{}' | Out-File -Encoding UTF8 $settings };" ^
  "$jsonText = Get-Content $settings -Raw;" ^
  "if ([string]::IsNullOrWhiteSpace($jsonText)) { $json = @{} } else { $json = $jsonText | ConvertFrom-Json };" ^
  "$json.'git.path' = '%GIT_CMD%';" ^
  "$json.'git.ssh.path' = '%SSH_DIR%\ssh.exe';" ^
  "if ($json.git.configLocation) { $json.git.configLocation = $null };" ^
  "$json.'python.defaultInterpreterPath' = '%PYTHON_PATH%';" ^
  "$json | ConvertTo-Json -Depth 10 | Out-File -Encoding UTF8 $settings"

REM 9. 公開鍵表示とGitHubサイトオープン (修正点)
echo ---------------------------------------
echo Public key for GitHub:
"%SSH_DIR%\ssh-keygen.exe" -y -f "%KEY_FILE%"
echo ---------------------------------------
echo "Copy this key to GitHub."

REM GitHub SSH設定ページを自動で開く
echo Opening GitHub SSH settings page..."https://github.com/settings/keys"

pause

REM 10. GitHub 接続テスト
echo Testing GitHub SSH connection...
"%SSH_DIR%\ssh.exe" -i "%KEY_FILE%" -T git@github.com
if ERRORLEVEL 1 (
    echo.
    echo WARNING: SSH connection failed. Check the key and GitHub settings.
    echo.
    echo (Note: The previous error "Permission denied" means your new key is NOT yet registered on GitHub.)
) else (
    echo.
    echo SUCCESS: GitHub SSH connection OK.
)

pause