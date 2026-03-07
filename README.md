# Develop
HouchiKoutei's develop lab

いろいろテストプログラムを作成しています。

以下、開発環境構築メモ

# 📱 スマホ Python 開発環境セットアップ

新しいAndroid端末に一瞬で Python 開発環境（Termux + Acode）を構築するためのスクリプトを提供します。

## 🚀 構築手順

### 1. 必要なアプリをインストール

以下のリンクから、アプリをインストールしてください。

| アプリ | リンク | 備考 |
| --- | --- | --- |
| **Termux** | [GitHub (最新版)](https://github.com/termux/termux-app/releases) | **※Google Play版は非推奨** |


 **※有料でAcodeというアプリもあるようです。** 
  [Google Play　Acode](https://play.google.com/store/apps/details?id=com.foxdebug.acode) 

### 2. セットアップスクリプトの実行

Termuxを起動し、以下のコマンドをコピーして貼り付けて実行してください。

**【実行コマンド】**

```bash
curl -O https://raw.githubusercontent.com/HouchiKoutei/Develop/main/Setup_SmartPhone.sh && chmod +x Setup_SmartPhone.sh && ./Setup_SmartPhone.sh

```

**【スクリプトの直リンク】**
ブラウザで内容を確認する場合はこちら：
`https://raw.githubusercontent.com/HouchiKoutei/Develop/main/Setup_SmartPhone.sh`

---