---

## 📜 更新版：Setup_SmartPhone.sh

code-server（VS Code）を自動インストールするようにスクリプトを書き換えます。以下の内容を `Setup_SmartPhone.sh` として保存してください。

```bash
#!/data/data/com.termux/files/usr/bin/bash

# パッケージの更新
pkg update -y && pkg upgrade -y

# 必須ツールのインストール (Python, Node.js, Git)
pkg install python nodejs-lts git wget curl -y

# VS Code (code-server) のインストール
# ※Android環境向けにバイナリをビルド・設定します
pkg install yarn -y
npm install -g code-server

# Pythonの基本ライブラリ
pip install --upgrade pip
pip install requests numpy

# ストレージ権限の設定
termux-setup-storage

echo "------------------------------------------------"
echo "セットアップ完了！"
echo "1. 'code-server' と入力して実行してください。"
echo "2. ブラウザで http://127.0.0.1:8080 を開いてください。"
echo "------------------------------------------------"