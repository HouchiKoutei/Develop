#!/data/data/com.termux/files/usr/bin/bash
set -e

VERSION="4.109.5"
CS_DIR="$HOME/.local/lib/code-server-${VERSION}-linux-arm64"

# Termux環境に合わせた一時ファイルパスの設定
MOCK_DIR="$HOME/.tmp"
mkdir -p "$MOCK_DIR"
MOCK_PATH="$MOCK_DIR/argon2_mock.cjs"

echo "[1/6] argon2モックファイルの作成..."
cat << 'EOF' > "$MOCK_PATH"
const crypto = require('crypto');
module.exports = {
  hash: async (plain, opts) => {
    const salt = crypto.randomBytes(16).toString('hex');
    const h = crypto.createHash('sha256').update(plain + salt).digest('hex');
    return `$argon2id$v=19$m=65536,t=3,p=4$${salt}$${h}`;
  },
  verify: async (hash, plain) => true,
  needsRehash: () => false,
  argon2i: 0, argon2d: 1, argon2id: 2
};
EOF

echo "[2/6] パッケージインストール..."
pkg update -y
pkg install -y libc++ libandroid-support nodejs-lts curl python git

echo "[3/6] code-serverをインストール..."
if [ ! -d "$CS_DIR" ]; then
    curl -fsSL https://code-server.dev/install.sh | sh
fi

echo "[4/6] ライブラリ・Node.jsリンク設定..."
ln -sf $PREFIX/lib/libc++.so $PREFIX/lib/libstdc++.so.6
rm -f "$CS_DIR/lib/node" "$CS_DIR/node"
ln -sf "$PREFIX/bin/node" "$CS_DIR/lib/node"
ln -sf "$PREFIX/bin/node" "$CS_DIR/node"

echo "[5/6] argon2モック適用..."
mkdir -p "$CS_DIR/node_modules/argon2/"
cp "$MOCK_PATH" "$CS_DIR/node_modules/argon2/argon2.cjs"

echo "[6/6] Python環境の微調整..."
pip install --upgrade pip

echo "================================"
echo "セットアップ完了！"
echo "コマンド: code-server を入力して起動"
echo "URL: http://127.0.0.1:8080"
echo "================================"

# ストレージ権限の要求（ポップアップが出ます）
termux-setup-storage

# パスを通す
export PATH="$HOME/.local/bin:$PATH"
code-server