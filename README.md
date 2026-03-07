# Develop
HouchiKoutei's develop lab

いろいろテストプログラムを作成しています。

以下、開発環境構築メモ

# 📱 スマホ Python 開発環境セットアップ

新しいAndroid端末に一瞬で Python 開発環境（Termux + Acode）を構築するためのスクリプトを提供します。

## 🚀 構築手順

### 1. 必要なアプリをインストール

以下のリンクから、2つの主要アプリをインストールしてください。

| アプリ | リンク | 備考 |
| --- | --- | --- |
| **Termux** | [GitHub (最新版)](https://github.com/termux/termux-app/releases) | **※Google Play版は非推奨** |
| **Acode** | [Google Play](https://play.google.com/store/apps/details?id=com.foxdebug.acode) | 高機能エディタ（**有料版/アプリ内課金あり**） |

### 2. セットアップスクリプトの実行

Termuxを起動し、以下のコマンドをコピーして貼り付けて実行してください。

**【実行コマンド】**

```bash
curl -LO https://raw.githubusercontent.com/HouchiKoutei/Develop/main/setup.sh && chmod +x setup.sh && ./setup.sh

```

**【スクリプトの直リンク】**
ブラウザで内容を確認する場合はこちら：
`https://raw.githubusercontent.com/HouchiKoutei/Develop/main/setup.sh`

---