#!/data/data/com.termux/files/usr/bin/bash
set -e

echo "================================================"
echo " code-server Python デバッグ環境セットアップ"
echo "================================================"

# ----------------------------
# [1/4] Open VSX をデフォルトに設定
# ----------------------------
echo ""
echo "[1/4] Open VSX Registryの設定..."

CONFIG_FILE="$HOME/.config/code-server/config.yaml"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "config.yamlが見つかりません。code-serverを一度起動してから再実行してください。"
    exit 1
fi

# すでに設定済みかチェック
if grep -q "open-vsx.org" "$CONFIG_FILE"; then
    echo "  → すでにOpen VSXが設定されています。スキップします。"
else
    cat >> "$CONFIG_FILE" << 'YAML_EOF'

# Open VSX Registry (MS Marketplace代替)
extensions-gallery:
  service-url: https://open-vsx.org/vscode/gallery
  item-url: https://open-vsx.org/vscode/item
YAML_EOF
    echo "  → Open VSX設定を追加しました。"
fi

# ----------------------------
# [2/4] debugpy のインストール（pip）
# ----------------------------
echo ""
echo "[2/4] debugpy (Pythonデバッグサーバー) のインストール..."

if python -c "import debugpy" 2>/dev/null; then
    echo "  → debugpy はすでにインストール済みです。スキップします。"
else
    pip install debugpy --break-system-packages
    echo "  → debugpy のインストール完了。"
fi

# ----------------------------
# [3/4] Python拡張機能のインストール（Open VSX経由）
# ----------------------------
echo ""
echo "[3/4] Python拡張機能のインストール（Open VSX経由）..."

install_ext() {
    EXT_ID="$1"
    EXT_NAME="$2"
    echo "  インストール中: $EXT_NAME ($EXT_ID)"
    if code-server --install-extension "$EXT_ID" 2>&1 | grep -q -E "(already installed|successfully installed|Extension .* is already)"; then
        echo "  → インストール済み or 完了"
    else
        code-server --install-extension "$EXT_ID" && echo "  → 完了" || echo "  → 失敗（スキップ）"
    fi
}

# Python本体拡張
install_ext "ms-python.python" "Python"
# debugpy拡張（デバッグUI）
install_ext "ms-python.debugpy" "Python Debugger (debugpy)"
# Pylance（あれば）
install_ext "ms-python.vscode-pylance" "Pylance" || true

# ----------------------------
# [4/4] launch.json のテンプレート生成
# ----------------------------
echo ""
echo "[4/4] launch.json テンプレートの生成..."

VSCODE_DIR="$HOME/.local/share/code-server/User"
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
# 完了メッセージ
# ----------------------------
echo ""
echo "================================================"
echo " セットアップ完了！"
echo "================================================"
echo ""
echo "【次のステップ】"
echo "  1. code-server を再起動してください："
echo "       pkill -f code-server && sleep 1 && code-server &"
echo ""
echo "  2. ブラウザで http://127.0.0.1:8080 を開く"
echo ""
echo "  3. デバッグしたいプロジェクトに .vscode/launch.json を置く："
echo "       cp -r ~/launch_template/.vscode /path/to/your/project/"
echo ""
echo "  4. Python拡張が入っていればF5キーでデバッグ開始！"
echo ""
echo "【もし拡張機能が動かない場合】"
echo "  以下コマンドで手動 debugpy デバッグが可能です："
echo "    python -m debugpy --listen 5678 --wait-for-client your_script.py"
echo "  その後、launch.json の 'Python: debugpy でアタッチ' を選んでF5"
echo "================================================"
EOF