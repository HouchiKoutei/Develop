#!/data/data/com.termux/files/usr/bin/bash
set -e

echo "================================================"
echo " code-server Python デバッグ環境セットアップ"
echo "================================================"

# ----------------------------
# [1/4] Open VSX の不要設定を除去
# ----------------------------
echo ""
echo "[1/5] config.yaml のクリーンアップ..."

CONFIG_FILE="$HOME/.config/code-server/config.yaml"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "config.yamlが見つかりません。code-serverを一度起動してから再実行してください。"
    exit 1
fi

# extensions-gallery 設定がある場合は削除（非対応のため）
if grep -q "extensions-gallery" "$CONFIG_FILE"; then
    # extensions-gallery ブロックを削除
    sed -i '/# Open VSX Registry/,/item-url:.*open-vsx/d' "$CONFIG_FILE"
    echo "  → 非対応のextensions-gallery設定を削除しました。"
else
    echo "  → クリーンな状態です。スキップします。"
fi

# ----------------------------
# [2/4] debugpy のインストール（pip）
# ----------------------------
echo ""
echo "[2/5] debugpy (Pythonデバッグサーバー) のインストール..."

if python -c "import debugpy" 2>/dev/null; then
    echo "  → debugpy はすでにインストール済みです。スキップします。"
else
    pip install debugpy --break-system-packages
    echo "  → debugpy のインストール完了。"
fi

# ----------------------------
# [3/4] Python拡張機能をVSIXで直接インストール
# ----------------------------
echo ""
echo "[3/5] Python拡張機能のインストール（Open VSX から VSIX直接取得）..."

VSIX_DIR="$HOME/.cache/code-server-vsix"
mkdir -p "$VSIX_DIR"

install_vsix() {
    PUBLISHER="$1"
    EXT_NAME="$2"
    DISPLAY_NAME="$3"
    VSIX_FILE="$VSIX_DIR/${PUBLISHER}.${EXT_NAME}.vsix"

    echo "  インストール中: $DISPLAY_NAME"

    # すでにインストール済みか確認
    if code-server --list-extensions 2>/dev/null | grep -qi "${PUBLISHER}.${EXT_NAME}"; then
        echo "  → すでにインストール済みです。スキップします。"
        return 0
    fi

    # Open VSX から最新バージョン情報を取得
    API_URL="https://open-vsx.org/api/${PUBLISHER}/${EXT_NAME}/latest"
    VSIX_URL=$(curl -sf "$API_URL" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    files = data.get('files', {})
    print(files.get('download', ''))
except:
    print('')
")

    if [ -z "$VSIX_URL" ]; then
        echo "  → URLの取得に失敗しました。スキップします。"
        return 1
    fi

    echo "  → ダウンロード中: $VSIX_URL"
    curl -fL "$VSIX_URL" -o "$VSIX_FILE" && \
        code-server --install-extension "$VSIX_FILE" && \
        echo "  → インストール完了" || \
        echo "  → インストール失敗（スキップ）"
}

install_vsix "ms-python" "python"  "Python"
install_vsix "ms-python" "debugpy" "Python Debugger (debugpy)"

# ----------------------------
# [4/4] launch.json のテンプレート生成
# ----------------------------
echo ""
echo "[4/5] launch.json テンプレートの生成..."

LAUNCH_DIR="$HOME/launch_template"
mkdir -p "$LAUNCH_DIR/.vscode"

cat > "$LAUNCH_DIR/.vscode/launch.json" << 'JSON_EOF'
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: 現在のファイルを実行",
            "type": "python",
            "request": "launch",
            "program": "${file}",
            "console": "integratedTerminal",
            "justMyCode": true
        },
        {
            "name": "Python: debugpy でアタッチ",
            "type": "python",
            "request": "attach",
            "connect": {
                "host": "127.0.0.1",
                "port": 5678
            },
            "justMyCode": true
        }
    ]
}
JSON_EOF

echo "  → テンプレートを ~/launch_template/.vscode/launch.json に生成しました。"
echo "     プロジェクトの .vscode/ フォルダにコピーして使ってください。"

# ----------------------------
# [5/5] code-server の起動
# ----------------------------
echo ""
echo "[5/5] code-server を起動中..."

# バックグラウンドで起動（ログをファイルに保存）
nohup "$HOME/.local/bin/code-server" > "$HOME/.code-server.log" 2>&1 &
sleep 3

# パスワードを表示
PASSWORD=$(grep 'password:' ~/.config/code-server/config.yaml 2>/dev/null | awk '{print $2}')

echo ""
echo "================================================"
echo " セットアップ完了！"
echo "================================================"
echo " URL:      http://127.0.0.1:8080"
echo " パスワード: $PASSWORD"
echo "------------------------------------------------"
echo " launch.json をプロジェクトに追加する場合："
echo "   cp -r ~/launch_template/.vscode /path/to/your/project/"
echo ""
echo " 手動 debugpy デバッグの場合："
echo "   python -m debugpy --listen 5678 --wait-for-client your_script.py"
echo "   → launch.json の 'Python: debugpy でアタッチ' を選んでF5"
echo "================================================"

# ブラウザを開く
termux-open-url "http://127.0.0.1:8080"

wait