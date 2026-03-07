#!/data/data/com.termux/files/usr/bin/bash

# パッケージの更新
apt update && apt upgrade -y

# 必須ツールのインストール
pkg install python git nano openssl curl -y

# Pythonライブラリの基本（必要に応じて追加）
pip install --upgrade pip
pip install requests numpy

# ストレージへのアクセス権限をリクエスト
termux-setup-storage

echo "------------------------------------------"
echo "Setup Complete! Python is ready."
echo "Use 'termux-setup-storage' to link with Acode."
echo "------------------------------------------"

