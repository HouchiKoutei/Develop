# Develop
HouchiKoutei's develop lab
# 📱 スマホ Python 開発環境セットアップ

新しいAndroid端末に一瞬で Python 開発環境（Termux + Acode）を構築するためのスクリプトを提供します。

## 🚀 構築手順

### 1. 必要なアプリをインストール

以下のリンクから、2つの主要アプリをインストールしてください。

| アプリ | リンク | 備考 |
| :--- | :--- | :--- |
| **Termux** | [GitHub (最新版)](https://github.com/termux/termux-app/releases) / [F-Droid](https://f-droid.org/ja/packages/com.termux/) | **※Google Play版は古いので非推奨です** |
| **Acode** | [Google Play](https://play.google.com/store/apps/details?id=com.foxdebug.acode) | 高機能なコードエディタ |

### 2. セットアップスクリプトの実行

Termuxを起動し、以下のコマンドをコピーして貼り付けて実行してください。

```bash
curl -O [https://raw.githubusercontent.com/](https://raw.githubusercontent.com/)[HouchiKoutei]/[Develop]/main/setup.sh && chmod +x setup.sh && ./setup.sh