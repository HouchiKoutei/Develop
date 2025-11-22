## 🛠️ Dify + Ollama 手動セットアップ手順 (Windows/Command Prompt環境)


この手順は、Geminiと相談してひととおりの動作確認後、Geminiに自動作成させています。
細かいところで間違いがあるかもしれませんので、ご指摘、質問はコメントでお知らせ願います。

### ステップ 1: 前提ソフトウェアの準備とインストール 💻

以下のソフトウェアをインストールします。ここでは、Windowsのパッケージマネージャー`winget`を使用したコマンドでのインストール方法を含めます。

| ソフトウェア | 目的 | インストールコマンド (PowerShell/CMD共通) |
| :--- | :--- | :--- |
| **Git** | Difyリポジトリのクローン | `winget install Git.Git` |
| **Docker Desktop** | Dockerコンテナの実行環境 | `winget install Docker.DockerDesktop` |
| **Ollama** | ローカルLLMの実行 | `winget install Ollama.Ollama` |

#### 1-1. 各ソフトウェアのインストール後の確認と初期設定

  * **Gitの確認:** コマンドプロンプトまたはPowerShellで以下を実行し、バージョン情報が表示されることを確認してください。
    ```bash
    git --version
    ```
  * **Docker Desktopの設定確認（WSL2バックエンドの有効化）**：
    1.  Docker Desktopを起動します。
    2.  タスクバーのクジラのアイコンを右クリックし、「**Settings**」を開きます。
    3.  左側のメニューで「**General**」を選択し、「**Use the WSL 2 based engine**」に**チェックが入っていること**を確認します。
    4.  左側のメニューで「**Resources**」→「**WSL INTEGRATION**」を選択し、使用するWSLディストリビューションが**有効になっていること**を確認します。
  * **Ollamaの確認:** インストール後、Ollamaが起動していることを確認してください。通常、PC起動時に自動でバックグラウンドサービスとして起動します。

-----

### ステップ 2: Docker Desktopの起動と安定化 🐳

Docker Desktopが完全に起動し、Docker Engineが利用可能な状態になるまで待ちます。

1.  Windowsに**ログイン**し、**Docker Desktop**アプリケーションを起動します。
2.  タスクバーの通知領域にある**クジラのアイコン🐳**が**緑色**に変わるまで待ちます。
3.  **管理者権限**でコマンドプロンプトを起動し、Dockerが応答するか確認します。

<!-- end list -->

```cmd
docker info
```

> **確認事項:** `docker info`を実行した際、エラーではなくDockerの情報（Containers, Images, Storage Driverなど）が表示されれば、次のステップに進んでください。

-----

### ステップ 3: Difyリポジトリのクローンと環境準備 📁

**管理者権限**でコマンドプロンプトを実行した状態で、以下の操作を実行します。

1.  Difyの作業フォルダとして`C:\Dify`を使用します。**もし`C:\Dify`フォルダが存在しない場合**は作成し、そのディレクトリに移動します。
※ 私の環境ではD:ドライブで実行した場合、うまくDifyサーバーが起動しませんでした。
<!-- end list -->

```cmd
:: C:\Dify フォルダに移動
mkdir C:\Dify
cd C:\Dify
```

2.  `C:\Dify`にDifyリポジトリをクローンし、`docker`フォルダへ移動します。

<!-- end list -->

```cmd
:: DifyリポジトリをC:\Dify\difyにクローン
git clone https://github.com/langgenius/dify.git dify

:: DifyのDocker設定フォルダに移動
cd dify\docker
```

3.  Docker Composeファイルを実行するための環境変数ファイルを用意します。

<!-- end list -->

```cmd
:: .env.exampleをコピーして.envを作成
copy .env.example .env
```

-----

### ステップ 4: Ollamaモデルのダウンロード 🤖

Ollamaがバックグラウンドで起動していることを確認してから、コマンドプロンプトでモデルをダウンロードします。

1.  使用したいモデルをダウンロードします。（例：`youri:7b-chat`）

<!-- end list -->

```cmd
:: 日本語対応モデルをダウンロード
ollama pull lambdalisue/youri:7b-chat

:: 汎用モデル (オプション)
ollama pull qwen2.5:3b
```

> **確認事項:** ダウンロードが完了し、`success`のようなメッセージが表示されるまでお待ちください。

-----

### ステップ 5: Dockerコンテナの起動 ▶️

**Difyの`docker`フォルダ**（`C:\Dify\dify\docker`）にいることを確認し、Docker Composeを実行します。

1.  Dockerコンテナ群をバックグラウンドで起動します。

<!-- end list -->

```cmd
:: -d はデタッチモード（バックグラウンド実行）
docker compose up -d
```

2.  すべてのコンテナが起動し、`Up`状態になるまで数分待ちます。以下のコマンドで状態を確認してください。

<!-- end list -->

```cmd
docker compose ps
```

> **確認事項:** `Status`列がすべて\*\*`running`**または**`Up`\*\*になっていることを確認してください。特にデータベースコンテナ（`docker-db-1`など）が安定するまで少し時間がかかります。

-----

### ステップ 6: Difyへのアクセスと設定 🌐

1.  Webブラウザで以下のURLにアクセスします。

<!-- end list -->

```
http://localhost/install
```

2.  **管理者アカウントを作成**し、Difyダッシュボードにログインします。
3.  **Ollamaの連携設定**：
      * Difyダッシュボード内で、**「設定 (Settings)」** → **「モデルプロバイダー (Model Providers)」** → **「Ollama」** の順に移動します。
      * **Base URL**のフィールドに、以下の値を設定します。

<!-- end list -->

```
http://host.docker.internal:11434
```

4.  設定を保存し、ダウンロードしたモデル（例：`youri:7b-chat`）を**有効化**します。

これで、DifyとOllamaを利用できる環境のセットアップが完了です。

-----

### 上記の動作の自動Power Shell Script
```
# =================================================================
# [Dify + Ollama Full Auto Setup] for Windows PowerShell
# -----------------------------------------------------------------
# CRITICAL: This script WILL force the working directory to C:\Dify
# to ensure stable Docker/PostgreSQL file I/O performance via WSL2.
# =================================================================
$ErrorActionPreference = "Stop"

# --------------------------------------------
# 固定ディレクトリの定義と移動
# --------------------------------------------
$FIXED_BASE_DIR = "C:\Dify" 
$SCRIPT_BASE_DIR = $FIXED_BASE_DIR 

# =========================
# Configurable variables
# =========================
$REPO_URL = "https://github.com/langgenius/dify.git"
$CLONE_DIR = "dify" # C:\Dify\dify にリポジトリがクローンされる
$LOG_FILE = ".\setup_dify_ollama_full.log" 
$DASHBOARD_URL = "http://localhost/install"
$MODELS = @("lambdalisue/youri:7b-chat", "qwen2.5:3b")
$DOCKER_WAIT_ATTEMPTS = 60 # 60 * 2sec = 120 seconds
$DOCKER_WAIT_SLEEP = 2

# Git Path Configuration (Portable Git/カスタムパスの場合に設定)
# 以前のログに基づき、D:\ProgramFiles\Coding\PortableGit\bin\ を保持
$GIT_EXEC_PATH = "D:\ProgramFiles\Coding\PortableGit\bin\" 
$GIT_EXE_FULL_PATH = Join-Path $GIT_EXEC_PATH "git.exe"

# Common Paths
$DockerPath = "C:\Program Files\Docker\Docker\resources\bin"
$OllamaPath = "$env:USERPROFILE\AppData\Local\Programs\Ollama"

$OllamaHost = "localhost"
$OllamaPort = 11434

# --------------------------------------------
# Helper Functions
# --------------------------------------------
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $LogMessage = "[$Level] $Message"
    Write-Host $LogMessage
    # ファイル書き込みはUTF8 BOM付きを使用（安定性向上）
    $LogMessage | Add-Content $LOG_FILE -Encoding UTF8
}

function Update-SessionPath {
    param([string]$ExecutableName, [string]$PathToCheck)

    if (-not (Get-Command $ExecutableName -ErrorAction SilentlyContinue) -and (Test-Path $PathToCheck)) {
        $env:Path = "$env:Path;$PathToCheck"
        Write-Log "$ExecutableName executable path added to current session's PATH." "Info"
        return $true
    }
    return $false
}

function Set-DockerAutostart {
    Write-Log "Setting Docker Desktop to start automatically..." "Setup"
    $DockerSettingsPath = Join-Path $env:APPDATA "Docker\settings.json"

    if (Test-Path $DockerSettingsPath) {
        try {
            $SettingsContent = Get-Content $DockerSettingsPath -Raw -Encoding UTF8
            $SettingsJson = $SettingsContent | ConvertFrom-Json -ErrorAction Stop

            if (-not $SettingsJson.startOnLogin -or $SettingsJson.startOnLogin -ne $true) {
                Write-Log "Modifying settings.json: setting startOnLogin to true." "Setup"
                $SettingsJson.startOnLogin = $true
                
                $SettingsJson | ConvertTo-Json -Depth 10 | Set-Content $DockerSettingsPath -Encoding UTF8
                Write-Log "Docker Desktop is now configured to start with Windows." "OK"
            } else {
                Write-Log "Docker Desktop is already configured to start with Windows." "OK"
            }
        } catch {
            Write-Log "Failed to modify Docker settings.json for autostart. Error: $($_.Exception.Message)" "Warn"
            Write-Log "Please set 'Start Docker Desktop when you log in' manually." "Warn"
        }
    } else {
        Write-Log "Docker settings file not found at '$DockerSettingsPath'. Cannot configure autostart." "Warn"
    }
}

function Invoke-FinalGuide {
    Write-Log "==============================================="
    Write-Log "### Final Setup Guide ###"

    $SERVER_IP = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias 'Wi-Fi*', 'Ethernet*' -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike "127.0.0.1" } | Select-Object -ExpandProperty IPAddress -First 1)

    Write-Log "**1. External Access (Same Network):**"
    if (-not [string]::IsNullOrEmpty($SERVER_IP)) {
        $EXTERNAL_URL = "http://$SERVER_IP/install"
        Write-Log " Access Address: Open **$EXTERNAL_URL** on a browser within the same network."
        Write-Log " Checkpoint: Ensure the server's firewall allows external access to **Port 80**."
    } else {
        Write-Log "[Warn] Could not automatically detect the server's local IP address." 
        Write-Log " Manual Step: Check your server's IP and open **http://[Your IP Address]/install**."
    }
    Write-Log ""

    Write-Log "**2. Post-Launch Configuration:**"
    Write-Log " a. **Admin Account Setup**: Create an admin account on the web interface."
    Write-Log " b. **Enable Ollama Model**:"
    Write-Log "  - Go to Dify: Settings -> Model Providers -> Ollama -> Configure."
    Write-Log "  - Set **Base URL** to **http://host.docker.internal:11434**."
    Write-Log "  - Enable the downloaded models ($($MODELS[0]) and $($MODELS[1])) for use."
    Write-Log ""
    Write-Log "==============================================="
}

# --------------------------------------------
# Main Script Logic
# --------------------------------------------

# --- Initialize Log File ---
"===============================================" | Out-File $LOG_FILE -Encoding UTF8
"[Dify + Ollama Full Auto Setup] (Windows PowerShell)" | Add-Content $LOG_FILE -Encoding UTF8
"Start time: $(Get-Date)" | Add-Content $LOG_FILE -Encoding UTF8
"Log: $($LOG_FILE)" | Add-Content $LOG_FILE -Encoding UTF8
"===============================================" | Add-Content $LOG_FILE -Encoding UTF8
Write-Log "PowerShell script started. Please ensure this session is running as Administrator."

# --- Fixed Directory Setup ---
Write-Log "Checking drive constraint: Target directory is $FIXED_BASE_DIR" "Setup"

if (-not (Test-Path $FIXED_BASE_DIR -PathType Container)) {
    Write-Log "Creating fixed directory: $FIXED_BASE_DIR" "Setup"
    try {
        New-Item -Path $FIXED_BASE_DIR -ItemType Directory -Force | Out-Null
    } catch {
        Write-Log "FATAL: Failed to create target directory '$FIXED_BASE_DIR'. Please ensure you run this script as Administrator." "Error"
        exit 1
    }
}

Write-Log "Changing current directory to: $FIXED_BASE_DIR" "Setup"
Set-Location -Path $FIXED_BASE_DIR

# --- Git Path Setup ---
Write-Log "Checking and setting Git executable path..."
if (-not [string]::IsNullOrEmpty($GIT_EXEC_PATH)) {
    if (-not (Test-Path $GIT_EXE_FULL_PATH)) {
        Write-Log "ERROR: Specified Git executable not found at '$GIT_EXE_FULL_PATH'. Please check \$GIT_EXEC_PATH." "Error"
        exit 1
    } else {
        Write-Log "Using specified Git executable: $GIT_EXE_FULL_PATH" "OK"
        Update-SessionPath -ExecutableName "git" -PathToCheck $GIT_EXEC_PATH
    }
} elseif (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Log "ERROR: Git command not found in PATH and \$GIT_EXEC_PATH is empty. Please install Git or set \$GIT_EXEC_PATH." "Error"
    exit 1
} else {
    $GIT_EXE_FULL_PATH = (Get-Command git).Source
    Write-Log "Using standard Git executable: $GIT_EXE_FULL_PATH" "OK"
}

# --- Git Security Fix ---
Write-Log "Applying Git security exception for Dify repository..." "Setup"
$DIFY_REPO_PATH_FIX = Join-Path $FIXED_BASE_DIR $CLONE_DIR 
try {
    & "$GIT_EXE_FULL_PATH" config --global --add safe.directory "$DIFY_REPO_PATH_FIX" | Out-Null
    Write-Log "Added '$DIFY_REPO_PATH_FIX' to Git safe directories." "OK"
} catch {
    Write-Log "Failed to apply Git safe directory fix, continuing." "Warn"
}

# --- Docker Desktop Check & Winget Installation ---
Write-Log "Checking Docker Desktop..."

$IsDockerRunning = $false
Update-SessionPath -ExecutableName "docker" -PathToCheck $DockerPath

try {
    docker info | Out-Null
    $IsDockerRunning = $true
    Write-Log "Docker Desktop is already running." "OK"
}
catch {
    $ErrorMessage = $_.Exception.Message
    
    if ($ErrorMessage -match "CommandNotFoundException" -or $ErrorMessage -match "The system cannot find the file specified") {
        Write-Log "Docker not fully operational. Attempting installation/repair via Winget..." "Info"
        
        try {
            Write-Log "Installing Docker Desktop. This requires Administrator privileges and may need a reboot." "Setup"
            winget install --id Docker.DockerDesktop -e --accept-package-agreements --accept-source-agreements --scope machine
            
            Update-SessionPath -ExecutableName "docker" -PathToCheck $DockerPath
            
            Set-DockerAutostart
            
            Write-Log "Docker Desktop installation command executed." "Warn"
            Write-Log "IMPORTANT: You MUST manually launch Docker Desktop once for initial setup." "Warn"
            
        } catch {
            Write-Log "Winget or Docker Desktop installation failed. Please install manually." "Error"
            exit 1
        }
    } else {
        Write-Log "Docker Desktop is installed but failed to run/connect. Please check the service status. Error: $($ErrorMessage)" "Error"
        exit 1
    }
}

# --- Wait for Docker Service to be Operational ---
if (-not $IsDockerRunning) {
    Write-Log "Waiting for Docker service to be fully operational (Max 120 seconds)..." "Wait"
    $Attempt = 0
    $WaitSuccess = $false
    do {
        Start-Sleep -Seconds $DOCKER_WAIT_SLEEP
        $Attempt++
        
        try {
            docker info | Out-Null
            $WaitSuccess = $true
            break
        } catch {
            Write-Log "Attempt $Attempt/${DOCKER_WAIT_ATTEMPTS}: Docker Engine not ready..." "Wait"
        }

        if ($Attempt -gt $DOCKER_WAIT_ATTEMPTS) {
            Write-Log "Docker Desktop did not become operational within the timeout. Exiting." "Error"
            exit 1
        }
    } while ($WaitSuccess -ne $true) 
    
    if ($WaitSuccess) {
        Write-Log "Docker Desktop is now operational." "OK"
    }
}

# --- Ollama Installation & Service Check (修正済み) ---
Write-Log "Checking Ollama installation..."
$OllamaInstalled = $true
$OllamaReachable = $false

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Log "Ollama not found. Attempting installation via Winget..." "Setup"
    try {
        winget install --id Ollama.Ollama -e --accept-package-agreements --accept-source-agreements
        Update-SessionPath -ExecutableName "ollama" -PathToCheck $OllamaPath
        Write-Log "Ollama installation command executed." "OK"
        
        # Ollamaサービスの起動を待機
        Write-Log "Waiting for Ollama service to start..." "Wait"
        $OllamaWaitAttempts = 30 # 60 seconds total wait
        $OllamaAttempt = 0
        $OllamaReachable = $false
        do {
            Start-Sleep -Seconds 2
            $OllamaAttempt++
            
            if ($OllamaAttempt -gt $OllamaWaitAttempts) {
                Write-Log "Ollama service did not become reachable. Proceeding, but model download may fail." "Warn"
                $OllamaInstalled = $false
                break
            }
            
            try {
                # Test-NetConnectionを使用してポート11434の接続を確認
                $ConnectionTest = Test-NetConnection -ComputerName $OllamaHost -Port $OllamaPort -InformationLevel Quiet -WarningAction SilentlyContinue | Select-Object -ExpandProperty TcpTestSucceeded
                
                if ($ConnectionTest -eq $True) {
                    Write-Log "Ollama service is reachable via port check." "OK"
                    $OllamaReachable = $true
                    break
                }
            } catch {
                # Test-NetConnection自体のエラー（稀）
            }
            Write-Log "Attempt {$OllamaAttempt}/{$OllamaWaitAttempts}: Ollama service not ready..." "Wait"
        } while ($OllamaReachable -ne $true)
        
    } catch {
        Write-Log "Winget or Ollama installation failed. Please install manually." "Error"
        $OllamaInstalled = $false
    }
} else {
    Write-Log "Ollama is already installed." "OK"
    $OllamaInstalled = $true
}

if ($OllamaInstalled) {
    Update-SessionPath -ExecutableName "ollama" -PathToCheck $OllamaPath | Out-Null

    Write-Log "Checking Ollama service responsiveness (ollama list)..."
    try {
        ollama list | Out-Null
        Write-Log "Ollama service is responsive and executable is in PATH." "OK"
    } catch {
        Write-Log "Ollama executable or service is unreachable. Model download will likely fail." "Warn"
    }
}


# --------------------------------------------
# Existing Environment Reset & Compose Directory Setup 
# --------------------------------------------
# Gitクローンの前に、リポジトリの絶対パスを取得しておく
$DIFY_ROOT_PATH = Join-Path $SCRIPT_BASE_DIR $CLONE_DIR
$DIFY_COMPOSE_DIR = ""

if (Test-Path $CLONE_DIR) {
    if (Test-Path (Join-Path $DIFY_ROOT_PATH "docker-compose.yaml")) { $DIFY_COMPOSE_DIR = $DIFY_ROOT_PATH }
    else { $DIFY_COMPOSE_DIR = Join-Path $DIFY_ROOT_PATH "docker" }

    Write-Host "Existing setup found. Reset and restart setup? (y/N)"
    $ResetChoice = Read-Host "Enter y to reset, or N to skip" 
    if ($ResetChoice -ceq "y") {
        Write-Log "Removing existing environment..." "Reset"
        if (-not [string]::IsNullOrEmpty($DIFY_COMPOSE_DIR) -and (Test-Path $DIFY_COMPOSE_DIR)) {
            try {
                Push-Location $DIFY_COMPOSE_DIR
                docker compose -f "docker-compose.yaml" down -v
                Pop-Location
            } catch {
                Write-Log "Docker down failed, continuing removal." "Warn"
                Pop-Location -ErrorAction SilentlyContinue
            }
        }
        Remove-Item $CLONE_DIR -Recurse -Force -ErrorAction SilentlyContinue
        $DIFY_COMPOSE_DIR = "" 
        Write-Log "$CLONE_DIR has been completely removed." "Reset"
    } else {
        Write-Log "Skipping environment reset and continuing setup." "Skip"
    }
}

# --- Dify Repository Clone/Update ---
$GIT_PULL_SUCCESS = $false

if (-not (Test-Path $GIT_EXE_FULL_PATH)) {
    Write-Log "Cannot proceed with Dify setup: Specified Git command is not available. Check \$GIT_EXEC_PATH." "Error"
    exit 1
}

if (-not (Test-Path $CLONE_DIR)) {
    Write-Log "Cloning Dify repository into $CLONE_DIR (Relative to $FIXED_BASE_DIR)..." "Setup"
    try {
        & "$GIT_EXE_FULL_PATH" clone $REPO_URL $CLONE_DIR | Add-Content $LOG_FILE -Encoding UTF8
        $GIT_PULL_SUCCESS = $true
        Write-Log "Dify repository cloned to: $FIXED_BASE_DIR\$CLONE_DIR" "OK"
    } catch {
        Write-Log "Failed to clone Dify repository. Exiting." "Error"
        exit 1
    }
} else {
    Write-Log "Updating Dify repository at $CLONE_DIR..." "Update"
    Push-Location $CLONE_DIR
    
    try {
        & "$GIT_EXE_FULL_PATH" pull origin main --ff-only | Add-Content $LOG_FILE -Encoding UTF8
        $GIT_PULL_SUCCESS = $true
        Write-Log "Dify repository updated cleanly." "OK"
    } catch {
        Write-Log "Standard Git pull failed. Attempting aggressive cleanup..." "Warn"
        
        try {
            & "$GIT_EXE_FULL_PATH" reset --hard origin/main | Add-Content $LOG_FILE -Encoding UTF8
            & "$GIT_EXE_FULL_PATH" clean -fd | Add-Content $LOG_FILE -Encoding UTF8
            & "$GIT_EXE_FULL_PATH" pull origin main | Add-Content $LOG_FILE -Encoding UTF8
            
            Write-Log "Aggressive Git cleanup successful." "OK"
            $GIT_PULL_SUCCESS = $true

        } catch {
            Write-Log "FATAL: Aggressive Git cleanup also failed." "Error"
            $GIT_PULL_SUCCESS = $false
        }
    }
    Pop-Location -ErrorAction SilentlyContinue
    
    if (-not $GIT_PULL_SUCCESS) {
        Write-Log "Cannot proceed with Dify setup. Please manually delete the '$CLONE_DIR' directory and run the script again." "Error"
        exit 1
    }
}

# --- .env Preparation ---
$DIFY_ROOT_PATH = Join-Path (Get-Location) $CLONE_DIR 

Write-Log "Determining Docker Compose directory path..." "Info"
if (Test-Path (Join-Path $DIFY_ROOT_PATH "docker-compose.yaml")) { 
    $DIFY_COMPOSE_DIR = $DIFY_ROOT_PATH
}
else { 
    $DIFY_COMPOSE_DIR = Join-Path $DIFY_ROOT_PATH "docker"
}

if (-not (Test-Path $DIFY_COMPOSE_DIR)) {
    Write-Log "Dify Docker Compose directory not found at '$DIFY_COMPOSE_DIR'. Exiting." "Error"
    exit 1
}

Write-Log "Docker Compose directory set to: $DIFY_COMPOSE_DIR" "OK" 

if (-not (Test-Path "$DIFY_COMPOSE_DIR\.env")) {
    Write-Log "Copying .env configuration from $DIFY_COMPOSE_DIR..." "Setup"
    Copy-Item (Join-Path $DIFY_COMPOSE_DIR ".env.example") (Join-Path $DIFY_COMPOSE_DIR ".env")
}

# --- Ollama Model Download ---
foreach ($MODEL_NAME in $MODELS) {
    Write-Log "Checking model '$MODEL_NAME'..." "Setup"
    
    $ModelExists = $false
    if ($OllamaInstalled -and $OllamaReachable) {
        try {
            $ModelExists = @(ollama list | Select-String $MODEL_NAME ).Count -gt 0
        } catch {
        }
    } 

    if (-not $ModelExists) {
        $ATTEMPTS = 0
        while ($true) {
            if (-not ($OllamaInstalled -and $OllamaReachable)) {
                Write-Log "Skipping model download for '$MODEL_NAME': Ollama is not installed or service is unreachable." "Skip"
                break
            }

            Write-Log "Downloading model '$MODEL_NAME'..." "Download"
            
            try {
                ollama pull $MODEL_NAME | Add-Content $LOG_FILE -Encoding UTF8
                Write-Log "Model '$MODEL_NAME' downloaded successfully." "OK"
                break
            } catch {
                Write-Log "Failed to download model '$MODEL_NAME'. (Ollama service may be unreachable)" "Warn"
                $ATTEMPTS++
                
                Write-Host "Model download failed. Choose one:"
                Write-Host "1) Manually enter model name and retry"
                Write-Host "2) Skip this model and continue"
                $Choice = Read-Host "Choice (1/2)"
                
                if ($Choice -eq "1") {
                    $UserModel = Read-Host "Enter the correct model name (e.g., llama3:8b)"
                    $MODEL_NAME = $UserModel 
                    continue
                } elseif ($Choice -eq "2") {
                    Write-Log "Skipping model download and continuing." "Skip"
                    break
                } else {
                    Write-Log "Invalid choice, skipping model download and continuing." "Skip"
                    break
                }
            }
        }
    } else {
        Write-Log "Model '$MODEL_NAME' already exists." "OK"
    }
}

# --- Docker Start ---
Write-Log "Starting Dify Docker containers..." "Setup"
$ComposeSuccess = $false
try {
    Push-Location $DIFY_COMPOSE_DIR
    docker compose up -d | Add-Content $LOG_FILE -Encoding UTF8
    Pop-Location
    $ComposeSuccess = $true
} catch {
    Write-Log "Failed to start Docker Compose. Check if Docker Desktop is running correctly." "Error"
    Invoke-FinalGuide 
    exit 1
}
if ($ComposeSuccess) {
    Write-Log "Checking database container health..." "Wait"
    $DB_CONTAINER = "docker-db-1"
    
    Start-Sleep -Seconds 10 
    
    try {
        Push-Location $DIFY_COMPOSE_DIR
        $DB_STATUS = docker compose ps -a $DB_CONTAINER --format "{{.State}}" 
        Pop-Location
        
        if ($DB_STATUS -match "exited" -or $DB_STATUS -match "unhealthy" -or $DB_STATUS -match "restarting") {
            Write-Log "Container '$DB_CONTAINER' failed with status: $DB_STATUS" "Error"
            Write-Log "--- DOCKER-DB-1 LOGS (CRITICAL ERROR) ---" "Error"
            
            $DB_LOGS = docker logs $DB_CONTAINER
            $DB_LOGS | ForEach-Object { Write-Log $_ "DB_LOG" }
            Write-Log "------------------------------------------" "Error"
            
            Write-Log "FATAL: Database container failed to start. Review logs above." "Error"
            Invoke-FinalGuide 
            exit 1
        } else {
            Write-Log "All essential containers started successfully (Status: $DB_STATUS)." "OK"
        }
    } catch {
        Write-Log "Could not check container status for '$DB_CONTAINER'. Continuing, but database may be unstable." "Warn"
    }
}

# --- Auto Open Browser (Local Access) ---
Write-Log "Dify Dashboard (Local Access): $DASHBOARD_URL" "Access"
Start-Process $DASHBOARD_URL -ErrorAction SilentlyContinue

# --- Final Guide ---
Invoke-FinalGuide

Write-Log "[Done] Dify + Ollama Full Auto Setup Complete"
Write-Log "==============================================="
``` 