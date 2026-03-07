#!/data/data/com.termux/files/usr/bin/bash
set -e

VERSION="4.109.5"
CS_DIR="$HOME/.local/lib/code-server-${VERSION}-linux-arm64"
TARBALL="$HOME/.cache/code-server/code-server-${VERSION}-linux-arm64.tar.gz"
MOCK_DIR="$HOME/.setup_tmp"
mkdir -p "$MOCK_DIR"
MOCK_PATH="$MOCK_DIR/argon2_mock.cjs"

echo "[1/5] argon2モックファイルの作成..."
cat > "$MOCK_PATH" << 'MOCK_EOF'
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
MOCK_EOF

echo "[2/5] パッケージインストール..."
pkg update -y
pkg install -y libc++ libandroid-support nodejs-lts curl python git

echo "[3/5] code-serverをインストール..."
if [ ! -f "$TARBALL" ]; then
    mkdir -p "$(dirname $TARBALL)"
    curl -fL "https://github.com/coder/code-server/releases/download/v${VERSION}/code-server-${VERSION}-linux-arm64.tar.gz" \
        -o "$TARBALL"
fi
rm -rf "$CS_DIR"
mkdir -p "$HOME/.local/lib" "$HOME/.local/bin"
tar -C "$HOME/.local/lib" \
    --no-same-owner \
    --warning=no-failed-read \
    -xzf "$TARBALL" 2>/dev/null || true
ln -sf "$CS_DIR/bin/code-server" "$HOME/.local/bin/code-server"

echo "[4/5] ライブラリ・Node.jsリンク設定..."
ln -sf $PREFIX/lib/libc++.so $PREFIX/lib/libstdc++.so.6
rm -f "$CS_DIR/lib/node" "$CS_DIR/node"
ln -sf "$PREFIX/bin/node" "$CS_DIR/lib/node"
ln -sf "$PREFIX/bin/node" "$CS_DIR/node"

echo "[5/5] argon2モック適用..."
cp "$MOCK_PATH" "$CS_DIR/node_modules/argon2/argon2.cjs"
rm -rf "$MOCK_DIR"

# 環境変数設定
export LD_LIBRARY_PATH="$PREFIX/lib:$LD_LIBRARY_PATH"
export PATH="$HOME/.local/bin:$PATH"

# .bashrcに永続化（なければ作成）
touch ~/.bashrc
grep -q 'LD_LIBRARY_PATH.*PREFIX' ~/.bashrc || \
    echo 'export LD_LIBRARY_PATH="$PREFIX/lib:$LD_LIBRARY_PATH"' >> ~/.bashrc
grep -q 'PATH.*local/bin' ~/.bashrc || \
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

# code-serverをバックグラウンドで起動
pkill -f code-server 2>/dev/null || true
sleep 1
"$HOME/.local/bin/code-server" &
sleep 3

PASSWORD=$(grep 'password:' ~/.config/code-server/config.yaml 2>/dev/null | awk '{print $2}')
echo "================================"
echo "セットアップ完了！"
echo "URL:      http://127.0.0.1:8080"
echo "パスワード: $PASSWORD"
echo "================================"

# ブラウザを開く
termux-open-url "http://127.0.0.1:8080"

wait