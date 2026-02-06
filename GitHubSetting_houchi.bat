@echo off
REM -------------------------------------------
REM USB Portable Git + SSH Setup for VSCode + GitHub Test
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
SET KEY_FILE=%KEY_DIR%\id_rsa
SET GIT_CMD=%GIT_DIR%\cmd\git.exe
SET VSCODE_DIR=%ROOT_DRIVE%\ProgramFiles\Coding\VSCode-win32-x64-1.103.0-insider
SET VSCODE_SETTINGS=%VSCODE_DIR%\data\user-data\User\settings.json
SET PORTABLE_GITCONFIG=%GIT_DIR%\portable_gitconfig
SET PYTHON_PATH=%ROOT_DRIVE%\ProgramFiles\Coding\WPy64-38100\python-3.8.10.amd64\python.exe

REM 4. グローバル SSH 設定を削除
%GIT_CMD% config --global --unset core.sshCommand

REM 5. パス確認
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

REM 6. SSHキー作成
if not exist "%KEY_DIR%" mkdir "%KEY_DIR%"
if not exist "%KEY_FILE%" (
    echo Generating SSH key...
    "%SSH_DIR%\ssh-keygen.exe" -t rsa -b 4096 -f "%KEY_FILE%" -C "%USER_EMAIL%" -N ""
) else (
    echo SSH key already exists.
)
REM 7. Portable Git config をグローバル設定として直接適用
echo [user] > "%GIT_DIR%\etc\gitconfig_temp"
echo     name = %USER_NAME% >> "%GIT_DIR%\etc\gitconfig_temp"
echo     email = %USER_EMAIL% >> "%GIT_DIR%\etc\gitconfig_temp"
echo [core] >> "%GIT_DIR%\etc\gitconfig_temp"
echo     sshCommand = "\"%SSH_DIR%\ssh.exe\" -i \"%KEY_FILE%\"" >> "%GIT_DIR%\etc\gitconfig_temp"

REM 既存のグローバル設定があれば削除し、新しい設定を強制適用
%GIT_CMD% config --global --unset-all user.name
%GIT_CMD% config --global --unset-all user.email
%GIT_CMD% config --global --unset-all core.sshCommand

%GIT_CMD% config --global user.name "%USER_NAME%"
%GIT_CMD% config --global user.email "%USER_EMAIL%"
%GIT_CMD% config --global core.sshCommand "\"%SSH_DIR%\ssh.exe\" -i \"%KEY_FILE%\""

REM 8. VSCode 設定更新
if not exist "%VSCODE_DIR%\data\user-data\User" mkdir "%VSCODE_DIR%\data\user-data\User"

powershell -NoProfile -ExecutionPolicy Bypass ^
  "$settings = '%VSCODE_SETTINGS%';" ^
  "if (!(Test-Path $settings)) { '{}' | Out-File -Encoding UTF8 $settings };" ^
  "$jsonText = Get-Content $settings -Raw;" ^
  "if ([string]::IsNullOrWhiteSpace($jsonText)) { $json = @{} } else { $json = $jsonText | ConvertFrom-Json };" ^
  "$json.'git.path' = '%GIT_CMD%';" ^
  "$json.'git.ssh.path' = '%SSH_DIR%\ssh.exe';" ^
  "$json.'git.configLocation' = '%PORTABLE_GITCONFIG%';" ^
  "$json.'python.defaultInterpreterPath' = '%PYTHON_PATH%';" ^
  "$json | ConvertTo-Json -Depth 10 | Out-File -Encoding UTF8 $settings"

REM 9. 公開鍵表示
echo ---------------------------------------
echo Public key for GitHub:
"%SSH_DIR%\ssh-keygen.exe" -y -f "%KEY_FILE%"
echo ---------------------------------------
echo "Copy this key to GitHub. Settings -> SSH and GPG keys -> New SSH Key"

pause

REM 10. GitHub 接続テスト
echo Testing GitHub SSH connection...
"%SSH_DIR%\ssh.exe" -i "%KEY_FILE%" -T git@github.com
if ERRORLEVEL 1 (
    echo.
    echo WARNING: SSH connection failed. Check the key and GitHub settings.
) else (
    echo.
    echo SUCCESS: GitHub SSH connection OK.
)

pause
