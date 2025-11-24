import ollama
import json
import time
import re
import subprocess
import sys
from datetime import datetime
from typing import Tuple, List, Dict, Any
import requests 
import os 

# ★★★ FastAPIサーバー設定の追加 ★★★
RAG_SERVER_URL = "http://127.0.0.1:8001" 
OLLAMA_SERVER_URL = "http://127.0.0.1:11434"

# RAG用プロンプトのテンプレート (大域変数)
RAG_PROMPT_TEMPLATE = """
以下の「参照ドキュメント」の内容に基づいて、「ユーザーの質問」に簡潔かつ正確に回答してください。
参照ドキュメントに情報がない場合は、その旨を正直に述べてください。

---
参照ドキュメント:
{context}
---
ユーザーの質問: {question}
"""
# ====================================================================
# I/O関数 (副作用あり)
# ====================================================================

def _wait_for_ollama_ready(host_url: str = OLLAMA_SERVER_URL, max_retries: int = 10, initial_delay: int = 2):
    """Ollamaサーバーが生存確認エンドポイントに応答するまで待機する (指数関数的バックオフ使用)"""
    for attempt in range(max_retries):
        try:
            # 最も軽量なヘルスチェック: ルートエンドポイントへのアクセス [5]
            response = requests.get(host_url, timeout=5)
            # Ollamaサーバーが起動し、応答しているかを確認
            if response.status_code == 200 and "Ollama is running" in response.text:
                return True
        except requests.exceptions.RequestException:
            # 接続エラー、またはサーバーがまだ応答していない場合
            pass

        # 指数関数的バックオフ [6]
        wait_time = initial_delay * (2 ** attempt)
        print(f"Ollama応答待ち ({host_url}). {wait_time}秒後に再試行します...")
        time.sleep(wait_time)
        
    raise ConnectionError("最大リトライ回数を超過してもOllamaサービスに接続できませんでした。")


def _start_ollama_server():
    """Ollamaサーバーが起動していない場合、subprocessで起動を試みます。"""
    try:
        # 既に起動しているか、listコマンドで確認
        subprocess.run(['ollama', 'list'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("Ollamaサーバーは既に起動しています。")
    except subprocess.CalledProcessError:
        try:
            # サーバー起動
            subprocess.Popen(['ollama', 'serve'], start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            # ★★★ 修正点1-B: 固定の sleep を準備完了ポーリングに置き換え [7] ★★★
            _wait_for_ollama_ready(OLLAMA_SERVER_URL)
            print("Ollamaサーバーを起動し、準備完了を確認しました。")
        except FileNotFoundError:
            print("エラー: 'ollama' コマンドが見つかりません。", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Ollamaサーバーの起動中に予期せぬエラーが発生しました: {e}")
            sys.exit(1)


def _pull_model_if_not_exists(model_name: str, client: Any) -> bool:
    """
    モデルの存在を確実に検証し、必要に応じて自動プルを行う関数。
    client.list()のカタログ不整合を回避するため、client.pull()を主要な検証手段とする。
    """
    
    print("-" * 30)
    print(f"DEBUG: 確認対象モデル: {model_name}")
    print("-" * 30)
    
    # 1. 検出とダウンロード/カタログ更新試行
    # 既にモデルが存在する場合、pullは即座に完了し、カタログの整合性を保証する [3, 4]
    print(f"モデル '{model_name}' の存在を確認/ダウンロードを試みます...")
    try:
        # client.pull()を実行
        for part in client.pull(model=model_name, stream=True):
             # 進行状況の表示は環境によって適宜調整
             if 'status' in part:
                 # print(f"プルステータス: {part['status']}", end='\r', flush=True)
                 pass
        
        print(f"\nモデル '{model_name}' の存在を確認しました。")
        return True

    except ConnectionError:
        # Ollamaサーバーへの接続に失敗した場合
        print(f"\nエラー: Ollamaサーバーへの接続に失敗しました。サーバーが実行中か、ホスト設定を確認してください。")
        return False
    except Exception as e:
        print(f"\nエラー: モデル '{model_name}' の取得中に予期せぬエラーが発生しました: {e}")
        return False


def _write_result_to_file(file_path: str, content: str):
    """結果を指定されたファイルに追記保存します。"""
    try:
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(content)
            f.write("\n\n" + "="*80 + "\n\n") 
        print(f"タスク結果を '{file_path}' に追記保存しました。")
    except Exception as e:
        # ファイル書き込みは致命的なエラーなので、標準の IOError で再発生させる
        raise IOError(f"ファイル '{file_path}' への書き込み中にエラーが発生しました: {e}")


    
# ====================================================================
# RAGサーバー クライアント関数 (rag_server_url を引数に追加)
# ====================================================================

def rag_server_register_files(file_paths: List[str], rag_server_url: str) -> bool:
    """FastAPIサーバーの /register エンドポイントを呼び出し、ファイルを登録します。
    サーバーからの応答メッセージを詳細に表示します。"""
    
    #... (ファイルの準備部分は変更なし)...
    # ※ 対策1-Bでファイルの存在チェックを強化していることを前提とします

    files_to_upload =[]
    for path in file_paths:
        try:
            files_to_upload.append(('files', (os.path.basename(path), open(path, 'rb'))))
        except FileNotFoundError:
            print(f"RAG: 警告: ファイル {path} が見つかりません。アップロードをスキップします。", file=sys.stderr)
            continue
        except Exception as e:
            print(f"RAG: 警告: ファイル {path} の準備中にエラーが発生しました: {e}", file=sys.stderr)
            continue

    if not files_to_upload:
        print("RAG: 警告: アップロードする有効なファイルがありません。RAGをスキップします。")
        return False

    print(f"RAG: サーバー ({rag_server_url}) に {len(files_to_upload)} 個のファイルを登録中...")
    try:
        url = f"{rag_server_url}/register"
        response = requests.post(url, files=files_to_upload, timeout=60)
        
        # 開いたファイルをすべてクローズ
        for _, (_, f) in files_to_upload:
            f.close()
            
        # サーバーからのJSONレスポンスを抽出
        try:
            result = response.json()
        except requests.exceptions.JSONDecodeError:
            # JSON形式でなかった場合、生のテキストを表示
            print(f"RAG: サーバー応答エラー (非JSON形式): HTTP {response.status_code}", file=sys.stderr)
            print(f"RAG: 応答本文: {response.text[:500]}", file=sys.stderr) # 500文字まで表示
            response.raise_for_status() # 念のためHTTPステータスをチェック
            return False

        # 応答が成功ステータス ('ok') の場合
        if result.get("status") == "ok":
            chunks_registered = result.get('chunks', 0)
            
            # ★★★ サーバーからの登録結果メッセージをそのまま表示 ★★★
            print(f"RAG: サーバー登録結果: {json.dumps(result, ensure_ascii=False)}")
            
            # チャンク数が0の場合、登録失敗と見なす
            if chunks_registered == 0:
                print("RAG: 警告: 登録チャンク数がゼロのため、RAGは無効です。")
                return False 
            return True
        
        # 応答がエラー ステータス ('error') の場合
        elif result.get("status") == "error":
            print(f"RAG: サーバー登録エラー (status=error):", file=sys.stderr)
            print(f"RAG: 応答メッセージ: {result.get('message', 'メッセージなし')}", file=sys.stderr)
            # サーバー側で発生したOllamaエラーなどを確認しやすくなります
            return False

        # 予期しないステータスの場合
        else:
            print(f"RAG: サーバー応答エラー (予期しないステータス): {json.dumps(result, ensure_ascii=False)}", file=sys.stderr)
            return False

    except requests.exceptions.HTTPError as e:
        # 4xx/5xx HTTPエラーの場合
        print(f"RAG: サーバー接続エラー (HTTP Error): {e}", file=sys.stderr)
        # 応答本文を表示してデバッグを容易にする
        print(f"RAG: エラー応答本文: {response.text[:500]}", file=sys.stderr)
        return False

    except requests.exceptions.RequestException as e:
        # 接続拒否、タイムアウトなどのネットワークエラーの場合
        print(f"RAG: サーバー接続または処理中にエラーが発生しました (ネットワーク/接続): {e}", file=sys.stderr)
        return False
    
def rag_server_query_context(query: str, rag_server_url: str, top_k: int = 4) -> str:
    """FastAPIサーバーの /query エンドポイントを呼び出し、関連コンテキストを取得します。"""
    if not query.strip():
        return ""

    print(f"RAG: サーバー ({rag_server_url}) でクエリを実行中...")
    try:
        url = f"{rag_server_url}/query" # ★★★ rag_server_url を使用 ★★★
        payload = {"query": query, "top_k": top_k}
        
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status() 
        result = response.json()
        
        count = result.get('count', 0)
        context = result.get('context', '')
        
        print(f"RAG: サーバーから {count} 個のコンテキストを取得しました。")
        return context

    except requests.exceptions.RequestException as e:
        print(f"RAG: サーバー接続またはクエリ中にエラーが発生しました: {e}")
        return ""

# ====================================================================
# RAG関連関数 (サーバーURLを引数で受け取るように変更)
# ====================================================================

def load_files_to_vector_db(file_paths: List[str], ollama_client: Any, rag_server_url: str) -> bool:
    """
    ファイルをFastAPIサーバーに登録します。
    """
    return rag_server_register_files(file_paths, rag_server_url)


def retrieve_context_from_db(query: str, db_status: bool, rag_server_url: str, top_k: int = 4) -> str:
    """
    FastAPIサーバーの /query を呼び出し、関連するコンテキストを取得します。
    """
    if not db_status: 
        return ""
    
    return rag_server_query_context(query, rag_server_url, top_k)

# ====================================================================
# コア機能関数 (プロンプトとURLを引数で受け取るように変更)
# ====================================================================

def generate_response(
    model_name: str, 
    prompt: str, 
    client: Any, 
    db_status: bool = False,
    rag_template: str = RAG_PROMPT_TEMPLATE, # ★★★ デフォルト値として大域変数を保持 ★★★
    rag_server_url: str = RAG_SERVER_URL     # ★★★ デフォルト値として大域変数を保持 ★★★
) -> Tuple[str, float]:
    """
    Ollamaモデルから回答を取得し、かかった時間を計測します。
    RAGが有効な場合、rag_server_urlを使用してコンテキストを取得します。
    """
    if not _pull_model_if_not_exists(model_name, client): 
        return f"[エラー: モデル '{model_name}' が見つからないか、ダウンロードに失敗しました。]", 0.0

    final_prompt = prompt
    is_rag_mode = False

    # RAGモードの場合のプロンプト構築
    if db_status:
        is_rag_mode = True
        
        # 1. サーバーからコンテキストを取得 (rag_server_url を使用)
        context = retrieve_context_from_db(prompt, db_status, rag_server_url) 
        
        if context:
            # 2. RAGテンプレート（引数で渡されたもの）にコンテキストと元の質問を埋め込む
            final_prompt = rag_template.format(context=context, question=prompt)
        else:
            print("RAG: コンテキストが取得できなかったため、RAGを無効化します。")
            
    start_time = time.time()
    try:
        mode_label = "RAG参照" if is_rag_mode else "非参照"
        print(f"モデル '{model_name}' ({mode_label}) で回答を生成中...")
        
        response = client.generate(
            model=model_name,
            prompt=final_prompt,
            stream=False 
        )
        latency = time.time() - start_time
        return response['response'].strip(), latency
    except Exception as e:
        latency = time.time() - start_time
        print(f"エラー: モデル '{model_name}' の応答取得中にエラーが発生しました: {e}")
        return f"[エラー: {e}]", latency
