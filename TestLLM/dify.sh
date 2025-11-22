#!/usr/bin/env bash
set -euo pipefail

# =========================
# 📝 Configurable variables
# =========================
REPO_URL="https://github.com/langgenius/dify.git"
CLONE_DIR="dify"
LOG_FILE="./setup_dify.log"
DASHBOARD_URL="http://localhost/install"

# Docker Check (for Mac/Linux)
DOCKER_WAIT_ATTEMPTS=60 # 60 * 2sec = 120秒
DOCKER_WAIT_SLEEP=2

# Dify Compose Path (自動判別用)
DIFY_COMPOSE_DIR=""

# --- ログファイル初期化 ---
echo "===============================================" | tee "$LOG_FILE"
echo "[Dify Auto Setup]" | tee -a "$LOG_FILE"
echo "Start time: $(date)" | tee -a "$LOG_FILE"
echo "Log: ${LOG_FILE}" | tee -a "$LOG_FILE"
echo "===============================================" | tee -a "$LOG_FILE"

# --------------------------------------------
# 🐳 Docker Desktop 起動チェック＆自動起動（Mac用）
# --------------------------------------------
echo "[Check] Docker Desktop..." | tee -a "$LOG_FILE"
if ! docker info >/dev/null 2>&1; then
  echo "[Info] Docker Desktop が起動していません。自動起動します..." | tee -a "$LOG_FILE"
  if [[ "$(uname)" == "Darwin" ]]; then
    open -a Docker
  else
    echo "[Warn] Docker Desktop の自動起動はMacでのみサポートされています。" | tee -a "$LOG_FILE"
    echo "       手動でDockerを起動し、このスクリプトを再実行してください。" | tee -a "$LOG_FILE"
    exit 1
  fi

  echo "[Wait] Docker が完全に起動するまで待機中..." | tee -a "$LOG_FILE"
  ATTEMPT=0
  until docker info >/dev/null 2>&1; do
    ((ATTEMPT++))
    if ((ATTEMPT > DOCKER_WAIT_ATTEMPTS)); then
      echo "[Error] Docker Desktop が起動しませんでした（タイムアウト）" | tee -a "$LOG_FILE"
      exit 1
    fi
    sleep "$DOCKER_WAIT_SLEEP"
  done
  echo "[OK] Docker Desktop が起動しました。" | tee -a "$LOG_FILE"
else
  echo "[OK] Docker Desktop はすでに起動しています。" | tee -a "$LOG_FILE"
fi

# --------------------------------------------
# 🔄 既存環境リセット確認 & Compose Directory 設定
# --------------------------------------------
if [ -d "$CLONE_DIR" ]; then
  if [ -f "${CLONE_DIR}/docker-compose.yaml" ]; then
    DIFY_COMPOSE_DIR="${CLONE_DIR}"
  else
    DIFY_COMPOSE_DIR="${CLONE_DIR}/docker"
  fi

  read -p "既存セットアップが検出されました。リセットして最初からやり直しますか？(y/N): " reset_choice
  if [[ "$reset_choice" =~ ^[Yy]$ ]]; then
    echo "[Reset] 既存環境を削除中..." | tee -a "$LOG_FILE"
    docker compose -f "${DIFY_COMPOSE_DIR}/docker-compose.yaml" down -v >/dev/null 2>&1 || true
    sudo rm -rf "$CLONE_DIR" || true
    DIFY_COMPOSE_DIR=""
    echo "[Reset] ${CLONE_DIR} を削除しました。" | tee -a "$LOG_FILE"
  else
    echo "[Skip] リセットをスキップし、セットアップを続行します。" | tee -a "$LOG_FILE"
  fi
fi

# --------------------------------------------
# ⬇️ Dify リポジトリ取得・更新
# --------------------------------------------
if [ ! -d "$CLONE_DIR" ]; then
  echo "[Setup] Dify リポジトリをクローン中..." | tee -a "$LOG_FILE"
  git clone "${REPO_URL}" "${CLONE_DIR}" 2>&1 | tee -a "$LOG_FILE"
  if [ -f "${CLONE_DIR}/docker-compose.yaml" ]; then
    DIFY_COMPOSE_DIR="${CLONE_DIR}"
  else
    DIFY_COMPOSE_DIR="${CLONE_DIR}/docker"
  fi
else
  echo "[Update] Dify リポジトリを更新中..." | tee -a "$LOG_FILE"
  (cd "$CLONE_DIR" && git pull origin main 2>&1 | tee -a "../$LOG_FILE")
fi

# --------------------------------------------
# 📝 .env 準備
# --------------------------------------------
if [ -z "$DIFY_COMPOSE_DIR" ]; then
  echo "[Error] DIFY_COMPOSE_DIR が設定されていません。" | tee -a "$LOG_FILE"
  exit 1
fi

if [ ! -f "${DIFY_COMPOSE_DIR}/.env" ]; then
  echo "[Setup] .env 設定をコピー中..." | tee -a "$LOG_FILE"
  cp "${DIFY_COMPOSE_DIR}/.env.example" "${DIFY_COMPOSE_DIR}/.env"
fi

# --------------------------------------------
# 🚀 Docker 起動
# --------------------------------------------
echo "[Setup] Dify Docker コンテナを起動中..." | tee -a "$LOG_FILE"
docker compose -f "${DIFY_COMPOSE_DIR}/docker-compose.yaml" up -d 2>&1 | tee -a "$LOG_FILE"

# --------------------------------------------
# 🌐 ブラウザ自動表示
# --------------------------------------------
echo "[Access] Dify ダッシュボード: ${DASHBOARD_URL}" | tee -a "$LOG_FILE"
if command -v open >/dev/null 2>&1; then
  open "${DASHBOARD_URL}"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "${DASHBOARD_URL}"
else
  echo "ブラウザで ${DASHBOARD_URL} を開いてください"
fi

# --------------------------------------------
# 🌍 外部アクセス手順
# --------------------------------------------
echo "===============================================" | tee -a "$LOG_FILE"
echo "### 外部PCからのアクセス手順 ###" | tee -a "$LOG_FILE"

SERVER_IP=$(ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -1 || ip addr show | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | cut -d/ -f1 | head -1)

if [ -n "$SERVER_IP" ]; then
  EXTERNAL_URL="http://${SERVER_IP}/install"
  echo "**💡 アクセスアドレス:**" | tee -a "$LOG_FILE"
  echo "  同一ネットワーク内のPCで以下を開いてください：" | tee -a "$LOG_FILE"
  echo "  ${EXTERNAL_URL}" | tee -a "$LOG_FILE"
  echo "" | tee -a "$LOG_FILE"
  echo "**✅ 確認事項:**" | tee -a "$LOG_FILE"
  echo "* サーバーPCのファイアウォールでポート80を許可してください。" | tee -a "$LOG_FILE"
else
  echo "[Warn] サーバーのローカルIPアドレスを自動検出できませんでした。" | tee -a "$LOG_FILE"
  echo "  手動で http://[あなたのIP]/install を開いてください。" | tee -a "$LOG_FILE"
fi

echo "===============================================" | tee -a "$LOG_FILE"
echo "[Done] ✅ Dify セットアップ完了 🎉" | tee -a "$LOG_FILE"