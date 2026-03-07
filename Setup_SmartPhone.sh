#!/data/data/com.termux/files/usr/bin/bash

# 1. パッケージの更新とビルド環境の準備
pkg update -y && pkg upgrade -y
pkg install build-essential binutils python-static-config-site-3.13 -y

# 2. 必須ツールのインストール
pkg install python nodejs-lts git wget curl -y

# 3. VS Code (code-server) のインストール
# 公式のインストールスクリプトを使用して環境に合わせたバイナリを配置します
curl -fsSL https://code-server.dev/install.sh | sh

# 4. Pythonライブラリのインストール
# (pip自体のアップグレードはTermuxではエラーになるため行いません)
pip install requests numpy

# 5. ストレージ権限の設定
termux-setup-storage

echo "------------------------------------------------"
echo "セットアップ完了！"
echo "1. 'code-server' と入力して実行してください。"
echo "2. 初回起動時に表示される 'Password' をコピーしてください。"
echo "3. ブラウザで http://127.0.0.1:8080 を開いてください。"
echo "------------------------------------------------"