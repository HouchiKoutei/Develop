import ollama
import json
import time
import subprocess
import sys
import os
import re
import string
from pathlib import Path
from datetime import datetime
from typing import Tuple, List, Dict, Any, Optional,Union
import requests 
import chardet
import csv
import tiktoken # トークン数を正確にカウントするために外部ライブラリを推奨
from tavily import TavilyClient

# --- パス設定 ---
source_directory = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(source_directory, "..", ".."))
sys.path.insert(0, project_root)


from Sources.Common import KeyManager 
from Sources.Common import FileControl

# ====================================================================
# I. グローバル設定とユーティリティ
# ====================================================================

# ★★★ FastAPIサーバー設定の追加 ★★★
RAG_SERVER_URL = "http://127.0.0.1:8001" 
OLLAMA_SERVER_URL = "http://127.0.0.1:11434"
TAVILY_CLIENT = None
INTERNET_CACHE_FILE = "./DocumentAuto/tavily_search_cache.json"

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

_MODEL_CONTEXT_LIMITS: Dict[str, int] = {

    # =========================
    # Meta Llama 系
    # =========================
    "llama3:8b": 8192,
    "llama3:70b": 8192,

    "llama3.1:8b": 8192,
    "llama3.1:70b": 8192,

    # Llama 3.2（軽量系）
    "llama3.2:3b": 8192,
    "llama3.2:1b": 8192,

    # =========================
    # Qwen 系（大コンテキスト）
    # =========================
    "qwen2:7b": 131072,
    "qwen2:14b": 131072,
    "qwen2:72b": 131072,

    "qwen2.5:7b": 131072,
    "qwen2.5:14b": 131072,
    "qwen2.5:32b": 131072,

    # Coder 特化
    "qwen2.5-coder:7b": 131072,
    "qwen2.5-coder:14b": 131072,
    "qwen2.5-coder:32b": 131072,
    "qwen3-coder:30b":262144,
    # =========================
    # Google Gemma 系
    # =========================
    "gemma2:2b": 8192,
    "gemma2:9b": 8192,
    "gemma2:27b": 8192,

    # =========================
    # Mistral 系
    # =========================
    "mistral:7b": 8192,
    "mistral-instruct:7b": 8192,

    "mixtral:8x7b": 32768,
    "mixtral:8x22b": 65536,

    # =========================
    # Code / Spec 特化
    # =========================
    "codellama:7b": 16384,
    "codellama:13b": 16384,
    "codellama:34b": 16384,

    # =========================
    # DeepSeek 系
    # =========================
    "deepseek-coder:6.7b": 16384,
    "deepseek-coder:33b": 16384,

    # =========================
    # その他
    # =========================
    "phi-3:mini": 4096,
    "phi-3:medium": 8192,

    # =========================
    # fallback
    # =========================
    "default_model": 4096,
}

# ====================================================================
# II. プロンプト/コンテキスト構築関数 (純粋)
# ====================================================================

def construct_rag_prompt(
    template: str,
    context: str, 
    question: str
) -> str:
    """
    RAGのテンプレート、取得したコンテキスト、質問を組み合わせて最終プロンプトを構築します。(純粋)
    """
    try:
        prompt = template.format(context=context, question=question)
    except KeyError as e:
        print(f"警告: RAGプロンプトテンプレートに必須のキーが不足しています: {e}", file=sys.stderr)
        prompt = f"{context}\n\n質問: {question}"
    return prompt

def get_context_window_size(model_name: str) -> int:
    """
    モデル名に基づいて、そのモデルの最大コンテキストウィンドウサイズ (トークン数) を取得します。
    """
    limit = _MODEL_CONTEXT_LIMITS.get(model_name)
    if limit is not None:
        return limit
    
    default_limit = _MODEL_CONTEXT_LIMITS.get("default_model", 4096)
    print(f"警告: モデル '{model_name}' のコンテキスト制限が見つかりません。デフォルト値 {default_limit} を使用します。", file=sys.stderr)
    return default_limit

def count_tokens(text: str, model_name: str) -> int:
    if "qwen" in model_name.lower():
        encoding = tiktoken.get_encoding("o200k_base")
    else:
        encoding = tiktoken.get_encoding("cl100k_base")
        
    return len(encoding.encode(text))

def _clean_text_output(text: str) -> str:
    """
    LLMの出力からMarkdownコードブロック（```, ```jsonなど）や前後の空白を除去する純粋関数。
    """
    if not isinstance(text, str):
        return ""
        
    text = text.strip()
    
    # 開始のコードブロックをチェックして除去
    if text.startswith(("```markdown", "```json", "```")):
        lines = text.splitlines()
        if len(lines) > 0 and lines[0].strip().startswith("```"):
            # 最初の行がコードブロック開始であれば除去
            text = "\n".join(lines[1:])
            
    # 終了のコードブロックをチェックして除去
    text = text.strip()
    if text.endswith("```"):
        text = text.strip()[:-3].strip()
        
    return text


# ====================================================================
# IV. I/O およびサーバー制御関数 (副作用あり)
# ====================================================================

def _wait_for_ollama_ready(host_url: str = OLLAMA_SERVER_URL, max_retries: int = 10, initial_delay: int = 2):
    """Ollamaサーバーが生存確認エンドポイントに応答するまで待機する (指数関数的バックオフ使用)"""
    for attempt in range(max_retries):
        try:
            response = requests.get(host_url, timeout=5)
            if response.status_code == 200 and "Ollama is running" in response.text:
                return True
        except requests.exceptions.RequestException:
            pass

        wait_time = initial_delay * (2 ** attempt)
        print(f"Ollama応答待ち ({host_url}). {wait_time}秒後に再試行します...", file=sys.stderr)
        time.sleep(wait_time)
        
    raise ConnectionError("最大リトライ回数を超過してもOllamaサービスに接続できませんでした。")


def _start_ollama_server():
    """Ollamaサーバーが起動していない場合、subprocessで起動を試みます。"""
    try:
        subprocess.run(['ollama', 'list'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("Ollamaサーバーは既に起動しています。", file=sys.stderr)
    except subprocess.CalledProcessError:
        try:
            subprocess.Popen(['ollama', 'serve'], start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            _wait_for_ollama_ready(OLLAMA_SERVER_URL)
            print("Ollamaサーバーを起動し、準備完了を確認しました。", file=sys.stderr)
        except FileNotFoundError:
            print("エラー: 'ollama' コマンドが見つかりません。", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Ollamaサーバーの起動中に予期せぬエラーが発生しました: {e}", file=sys.stderr)
            sys.exit(1)

def initialize_ollama_client(url: str = OLLAMA_SERVER_URL):
    """Ollamaクライアントを初期化し、サーバーが利用可能であることを確認する (外部関数の代替)"""
    _start_ollama_server()
    try:
        client = ollama.Client(host=url)
        print(f"Ollamaクライアントを {url} で初期化しました。", file=sys.stderr)
        return client
    except Exception as e:
        raise ConnectionError(f"Ollama接続失敗 {e}")
    
def _pull_model_if_not_exists(model_name: str, client: Any) -> bool:
    """
    モデルの存在を検証し、数値のNoneチェックを行いながらプログレスバーを表示してプルします。
    """
    try:
        # 存在確認
        result = subprocess.run(
            ["ollama", "show", model_name],
            capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            print(f"✅ モデル '{model_name}' は既にローカルに存在します。", file=sys.stderr)
            return True
    except Exception as e:
        print(f"モデル検証中にエラーが発生しました: {e}", file=sys.stderr)

    print(f"📥 モデル '{model_name}' が見つかりません。ダウンロードを開始します...", file=sys.stderr)
    
    try:
        current_digest = ""
        for part in client.pull(model=model_name, stream=True):
            status = part.get('status', '')
            total = part.get('total')      # Noneの可能性がある
            completed = part.get('completed') # Noneの可能性がある
            
            # 数値が有効(Noneでない)かつ、ダウンロード中であるかチェック
            if total is not None and completed is not None and total > 0:
                percent = int(completed / total * 100)
                bar_length = 40
                filled_length = int(bar_length * completed // total)
                bar = '█' * filled_length + '-' * (bar_length - filled_length)
                
                completed_gb = completed / (1024**3)
                total_gb = total / (1024**3)
                
                # \r で同じ行を上書き
                sys.stdout.write(f"\r|{bar}| {percent}% ({completed_gb:.2f}/{total_gb:.2f} GB) {status}")
                sys.stdout.flush()
            else:
                # 数値が取れない場合や、ステータスが変わった場合はテキストのみ表示
                if status != current_digest:
                    # 前のバーの残りを消すために空白を入れてから出力
                    sys.stdout.write(f"\r{' ' * 80}\r") 
                    print(f"{status}", file=sys.stderr)
                    current_digest = status

        print(f"\n✅ モデル '{model_name}' の取得が完了しました。", file=sys.stderr)
        return True

    except Exception as e:
        print(f"\n❌ モデルの取得中にエラーが発生しました: {e}", file=sys.stderr)
        return False

def _write_result_to_file(file_path: str, content: str,add_mode:bool = False):
    """結果を指定されたファイルに保存します。"""
    if not content:
        content=""
    if add_mode:
        mode = "a"
    else:
        mode = "w"
    try:
        with open(file_path, mode, encoding='utf-8') as f:
            f.write(content)
            f.write("\n\n" + "="*80 + "\n\n") 
        print(f"タスク結果を '{file_path}' に保存しました。", file=sys.stderr)
    except Exception as e:
        raise IOError(f"ファイル '{file_path}' への書き込み中にエラーが発生しました: {e}")

def read_previous_output(file_path: str) -> str:
    """
    前のタスクの出力ファイルを読み込み、その内容を返す。（I/O）
    """
    try:
        _, ext = os.path.splitext(file_path.lower())

        if ext == '.csv':
            return read_csv_with_auto_encoding(file_path)
        else:
            return read_text_with_auto_encoding(file_path)

    except FileNotFoundError:
        print(f"警告: 入力ファイル {file_path} が見つかりません。", file=sys.stderr)
        return ""
    
    except Exception as e:
        print(f"エラー: ファイルの読み込み中に予期せぬエラーが発生しました: {e}", file=sys.stderr)
        return ""
    
def read_text_with_auto_encoding(file_path: str):
    # 1. ファイルをバイナリモードで読み込む
    raw_data = None
    with open(file_path, 'rb') as f:
        raw_data = f.read(10000) 

    # 2. chardetでエンコーディングを推定
    result = chardet.detect(raw_data)
    detected_encoding = result['encoding']
    confidence = result['confidence']
    
    # 3. 推定されたエンコーディングでファイルを読み込む
    if confidence > 0.8 and detected_encoding:
        print(f"{file_path}のエンコーディングを {detected_encoding} ({confidence:.2f}) と推定しました。", file=sys.stderr)
        try:
            with open(file_path, 'r', encoding=detected_encoding, errors='ignore') as f:
                content = f.read()
            return content
        except Exception as e:
            print(f"エラー: 推定されたエンコーディングでの読み込みに失敗しました: {e}", file=sys.stderr)
            return None
    else:
        print("警告: エンコーディングの判別に失敗しました。デフォルトのUTF-8で試行します。", file=sys.stderr)
        try:
            with open(file_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
                content = f.read()
            return content
        except:
            print("警告: エンコーディングの判別に失敗しました。", file=sys.stderr)
            return None 

def read_csv_with_auto_encoding(file_path: str):
    if not os.path.exists(file_path):
        print(f"警告: ファイル {file_path} が見つかりません。", file=sys.stderr)
        return None

    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read(100000) 

        result = chardet.detect(raw_data)
        detected_encoding = result['encoding']
        confidence = result['confidence']
        
        if detected_encoding and confidence > 0.8:
            encoding_to_use = detected_encoding
        else:
            encoding_to_use = 'utf-8-sig'
        
        print(f"{file_path}のエンコーディングを '{encoding_to_use}' (信頼度: {confidence:.2f}) と推定して読み込みます。", file=sys.stderr)

    except Exception as e:
        print(f"エラー: エンコーディングの自動判別に失敗しました: {e}", file=sys.stderr)
        return None

    csv_data = []
    try:
        with open(file_path, 'r', encoding=encoding_to_use, newline='', errors='ignore') as f:
            reader = csv.reader(f)
            for row in reader:
                csv_data.append(row)
        
        # CSVデータをテキスト形式に変換して返す（プロンプトに含めるため）
        csv_text = "\n".join([",".join(map(str, row)) for row in csv_data])
        return csv_text
        
    except Exception as e:
        print(f"エラー: CSVファイルの読み込みに失敗しました: {e}", file=sys.stderr)
        return None


def lazy_load_tavily_client(encrypted_secrets_path: str) -> Optional[TavilyClient]:
    """
    マスターキー入力を含むAPIキーの復号化とTavilyClientの初期化を遅延実行します。（I/O）
    """
    global TAVILY_CLIENT
    
    if TAVILY_CLIENT:
        return TAVILY_CLIENT

    print("\n--- Tavily APIキーを復号化します (マスターキーの入力が必要です) ---", file=sys.stderr)
    
    try:
        # KeyManagerがローカルにあることを想定
        TAVILY_API_KEY_HOLDER = KeyManager.decrypt_api_keys(encrypted_secrets_path) 
        TAVILY_API_KEY = TAVILY_API_KEY_HOLDER.get('tavily_api_key') if TAVILY_API_KEY_HOLDER else None
        
        if TAVILY_API_KEY:
            cleaned_key = TAVILY_API_KEY.strip()
            TAVILY_CLIENT = TavilyClient(api_key=cleaned_key)
            print("Tavilyクライアントが正常に初期化されました。", file=sys.stderr)
            return TAVILY_CLIENT
        else:
            print("警告: 復号化されたデータからTavily APIキーを取得できませんでした。", file=sys.stderr)
            return None
            
    except Exception as e:
        print(f"エラー: Tavilyクライアントの初期化/復号化に失敗しました: {e}", file=sys.stderr)
        return None

def load_search_cache(cache_file_path: str) -> Dict[str, str]:
    """
    検索キャッシュファイル（JSON形式）を読み込み、クエリ:結果の辞書を返します。（I/O）
    """
    cache = {}
    if not os.path.exists(cache_file_path):
        return cache
        
    try:
        with open(cache_file_path, 'r', encoding='utf-8') as f:
            cache = json.load(f)
        
        if not isinstance(cache, dict):
            print(f"警告: キャッシュファイル {cache_file_path} の形式が正しくありません。", file=sys.stderr)
            return {}
            
        print(f"検索キャッシュを {len(cache)} 件ロードしました。", file=sys.stderr)
    except json.JSONDecodeError as e:
        print(f"警告: 検索キャッシュのデコードに失敗しました (JSON形式エラー): {e}", file=sys.stderr)
        return {}
    except Exception as e:
        print(f"警告: 検索キャッシュのロードに失敗しました: {e}", file=sys.stderr)
    return cache

def save_search_cache(cache_file_path: str, cache_data: Dict[str, str]):
    """
    検索キャッシュ辞書をファイル（JSON形式）に書き込みます。（I/O）
    """
    os.makedirs(os.path.dirname(cache_file_path), exist_ok=True)
    try:
        with open(cache_file_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=4) 
            
        print(f"検索キャッシュを {len(cache_data)} 件保存しました。{cache_file_path}", file=sys.stderr)
    except Exception as e:
        print(f"エラー: 検索キャッシュの保存に失敗しました: {e}", file=sys.stderr)


def get_or_fetch_search_context(question: str, encrypted_secrets_path: str, internet_search_cash_file_path: str) -> str:
    """
    キャッシュをチェックし、存在しなければTavily検索を実行して結果を取得・キャッシュします。（I/O）
    """
    global TAVILY_CLIENT
    
    # 1. キャッシュのロード
    cache = load_search_cache(internet_search_cash_file_path)
    if question in cache:
        print("✅ キャッシュから検索コンテキストを取得しました。", file=sys.stderr)
        return cache[question] # ヘッダー/フッターは呼び出し元で追加
    
    # 2. Tavilyクライアントを遅延ロード
    TAVILY_CLIENT = lazy_load_tavily_client(encrypted_secrets_path)
    if TAVILY_CLIENT is None:
        print("警告: Tavilyクライアントの初期化に失敗したため、インターネット検索をスキップします。", file=sys.stderr)
        return ""
    
    # 3. Tavily検索の実行
    print("インターネット検索 (Tavily) を実行中...", file=sys.stderr)
    try:
        search_results = TAVILY_CLIENT.search(
            query=question,
            search_depth="advanced", 
            max_results=5 
        )
        
        context_parts = []
        
        for i, result in enumerate(search_results.get('results', []), 1):
            context_parts.append(
                f"--- 検索結果 {i} ({result.get('title', 'N/A')}) ---\n"
                f"URL: {result.get('url', 'N/A')}\n"
                f"内容: {result.get('summary', 'N/A')}\n"
            )

        final_answer = search_results.get('answer')
        if final_answer:
            context_parts.insert(0, f"--- Tavilyによる要約回答 ---\n{final_answer}\n---")
            
        
        if context_parts:
            context = "\n".join(context_parts)
            print("インターネット検索コンテキストを取得しました。", file=sys.stderr)
            
            # 4. キャッシュに保存
            cache[question] = context
            save_search_cache(internet_search_cash_file_path, cache)
            
            return context
        else:
            print("インターネット検索結果は得られませんでした。", file=sys.stderr)
            return ""

    except Exception as e:
        print(f"エラー: Tavily Searchの実行中にエラーが発生しました: {e}", file=sys.stderr)
        return ""

# ====================================================================
# RAGサーバー クライアント関数 (変更なし)
# ====================================================================

def rag_server_register(path_list: Union[str,List[str]], rag_server_url: str) -> bool:
    """FastAPIサーバーの /register エンドポイントを呼び出し、ファイルを登録します。"""
    files_to_upload =[]

    file_paths = FileControl.get_file_path_list(path_list, recursive = True)
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
        print("RAG: 警告: アップロードする有効なファイルがありません。RAGをスキップします。", file=sys.stderr)
        return False

    print(f"RAG: サーバー ({rag_server_url}) に {len(files_to_upload)} 個のファイルを登録中...", file=sys.stderr)
    try:
        url = f"{rag_server_url}/register"
        response = requests.post(url, files=files_to_upload, timeout=60)
        
        for _, (_, f) in files_to_upload:
            f.close()
            
        try:
            result = response.json()
        except requests.exceptions.JSONDecodeError:
            print(f"RAG: サーバー応答エラー (非JSON形式): HTTP {response.status_code}", file=sys.stderr)
            print(f"RAG: 応答本文: {response.text[:500]}", file=sys.stderr) 
            response.raise_for_status() 
            return False

        if result.get("status") in ["ok","success", "accepted"]:
            chunks_registered = result.get('chunks',result.get('files',0))
            print(f"RAG: サーバー登録結果: {json.dumps(result, ensure_ascii=False)}", file=sys.stderr)
            if chunks_registered == 0:
                print("RAG: 警告: 登録チャンク数がゼロのため、RAGは無効です。", file=sys.stderr)
                return False 
            return True
        
        elif result.get("status") == "error":
            print(f"RAG: サーバー登録エラー (status=error):", file=sys.stderr)
            print(f"RAG: 応答メッセージ: {result.get('message', 'メッセージなし')}", file=sys.stderr)
            return False

        else:
            print(f"RAG: サーバー応答エラー (予期しないステータス): {json.dumps(result, ensure_ascii=False)}", file=sys.stderr)
            return False

    except requests.exceptions.HTTPError as e:
        print(f"RAG: サーバー接続エラー (HTTP Error): {e}", file=sys.stderr)
        print(f"RAG: エラー応答本文: {response.text[:500]}", file=sys.stderr)
        return False

    except requests.exceptions.RequestException as e:
        print(f"RAG: サーバー接続または処理中にエラーが発生しました (ネットワーク/接続): {e}", file=sys.stderr)
        return False
    
def rag_server_query_context(
    query: str,
    rag_server_url: str,
    top_k: Optional[int] = None,
    score_threshold: Optional[float] = None
) -> str:
    if not query.strip():
        return ""

    print(f"RAG: サーバー ({rag_server_url}) でクエリを実行中...", file=sys.stderr)
    try:
        url = f"{rag_server_url}/query"

        payload = {"query": query}
        if top_k is not None:
            payload["top_k"] = top_k
        if score_threshold is not None:
            payload["score_threshold"] = score_threshold

        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()

        count = result.get("count", result.get("hit_count", 0))
        contexts = result.get("contexts", [])
        if count == 0:
            print(f"RAG: 関連コンテキストなし{result}", file=sys.stderr)
            return ""

        print(f"RAG: {count} 件取得（threshold={score_threshold}）", file=sys.stderr)
        joined = "\n\n".join(c["text"] for c in contexts if "text" in c)
        return joined
    
    except requests.exceptions.RequestException as e:
        print(f"RAG: エラー: {e}", file=sys.stderr)
        return ""

# ====================================================================
# VI. マルチソース分析オーケストレーション関数
# ====================================================================

def _get_safe_inheritance_data(ctx_data: Any, model_name: str, max_tokens: int) -> str:
    """継承データを文字列化し、トークン制限を超えた場合に先頭を切り詰める"""
    if not ctx_data:
        return ""
    
    data_str = ctx_data if isinstance(ctx_data, str) else json.dumps(ctx_data, ensure_ascii=False)
    current_tokens = count_tokens(data_str, model_name)
    
    if current_tokens > max_tokens:
        print(f"DEBUG: 継承データが制限({max_tokens})を超えたため切り詰めます。", file=sys.stderr)
        ratio = max_tokens / current_tokens
        cut_index = int(len(data_str) * (1 - ratio))
        return "...(Truncated)...\n" + data_str[cut_index:]
    
    return data_str

def _find_token_boundary_index(text: str, limit: int, model_name: str, from_end: bool = False) -> int:
    """指定トークン数に収まる文字数のインデックスを二分探索で返す"""
    low, high = 0, len(text)
    best_idx = 0 if from_end else 0
    
    while low <= high:
        mid = (low + high) // 2
        test_chunk = text[-mid:] if from_end else text[:mid]
        if count_tokens(test_chunk, model_name) <= limit:
            best_idx = mid
            low = mid + 1
        else:
            high = mid - 1
    return best_idx

def get_chunk_by_token_limit(text: str, limit: int, model_name: str) -> Tuple[str, str]:
    idx = _find_token_boundary_index(text, limit, model_name)
    return text[:idx], text[:idx]

def get_last_n_tokens_text(text: str, n: int, model_name: str) -> str:
    idx = _find_token_boundary_index(text, n, model_name, from_end=True)
    return text[-idx:] if idx > 0 else ""

def build_prompt(template_list, **kwargs):
    """
    テンプレートリストを結合し、kwargsで渡された値で穴埋めする。
    値が渡されていない変数が含まれる行は、エラーにせずそのまま残すか、
    あるいは「空」として扱う制御が可能。
    """
    resolved_lines = []
    
    for line in template_list:
        # この行に必要な変数名（{chunk}など）をリストアップ
        field_names = [fname for _, fname, _, _ in string.Formatter().parse(line) if fname]
        
        # データの整形（辞書・リストはJSON化、未指定の変数は "" で代用）
        render_data = {}
        for name in field_names:
            val = kwargs.get(name)
            if val is None:
                render_data[name] = "" # カウント時はここが空になる
            elif isinstance(val, (dict, list)):
                render_data[name] = json.dumps(val, ensure_ascii=False, indent=2)
            else:
                render_data[name] = str(val)
        
        # 穴埋め実行
        resolved_lines.append(line.format(**render_data))
        
    return "\n\n".join(resolved_lines)

def execute_llm_request(
    ollama_client: Any,
    model_name: str,
    question:str ,
    prompt: str="",
    system_prompt: str="",
    assistant_message: str="",
    format: Optional[str] = None,
    stream: bool = False,
    use_chat: bool = True,
    options: Optional[Dict[str, Any]] = None
) -> str:
    """
    OllamaのChatとGenerateの違いを吸収して実行し、テキスト結果を返す。
    """
    # optionsがNoneや文字列の場合に空辞書に変換（エラー対策）
    safe_options = options if isinstance(options, dict) else {}
    
    # 1. 共通の引数設定
    api_kwargs = {
        'model': model_name,
        'stream': stream,
        'format': format,
        'options': safe_options
    }

    # 2. メソッドと特有の引数を設定
    if use_chat:
        api_method = ollama_client.chat
        # full_prompt_or_messages がリストであることを確認
        if not isinstance(question, list):
            # 文字列で渡された場合はユーザーメッセージとして包む
            api_kwargs['messages'] = [{'role': 'system', 'content': str(system_prompt)}]
            if assistant_message:
                api_kwargs['messages'].append({'role': 'assistant', 'content': str(assistant_message)})
            api_kwargs['messages'].append({'role': 'user', 'content': str(question)+str(prompt)})

        else:
            api_kwargs['messages'] = question

    else:
        api_method = ollama_client.generate
        # 文字列であることを確認
        api_kwargs['prompt'] = str(question)+"\n"+str(system_prompt)+"\n"+str(prompt)

    # 3. 実行
    response = api_method(**api_kwargs)

    # 4. レスポンスのパース
    if stream:
        result = []
        for chunk in response:
            if use_chat:
                # chatの場合は message -> content
                content = chunk.get('message', {}).get('content', '')
            else:
                # generateの場合は response
                content = chunk.get('response', '')
            result.append(content)
        return "".join(result).strip()
    else:
        if use_chat:
            return response.get('message', {}).get('content', "").strip()
        else:
            return response.get('response', "").strip()

def answer_question(
    question: str,
    data_source: str, 
    model_name: str, 
    ollama_client: Any, 
    overlap_tokens: int = 100,
    prompt: str = "・以下の[参照データ]について回答を生成してください。",
    prompt_data_tytle: str = f"[参照データ]\n",
    format: Optional[Dict[str, Any]] = None,
    prev_response: Optional[Any] = None, # 過去の回答全体、またはKey付きオブジェクト
    prev_response_key: str = "",            # 特定のKeyを抽出する場合に指定
    evaluation_feedback: str = "", 
    stream: bool = False,
    use_chat: bool = True,
    options: Optional[Dict[str, Any]] = {'temperature': 0.1},
    max_inheritance_tokens: int = 2000,
) -> List[Any]:
    
    if not _pull_model_if_not_exists(model_name, ollama_client):
        return [f"[エラー: モデル '{model_name}' が利用できません。]"]
        
    current_context_data = prev_response
    answer_chunks: List[Any] = []
    remaining_data = data_source
    iteration = 0
    
    while len(remaining_data) > 0:
        iteration += 1
        
        # --- 1. assistant_message (過去のコンテキスト) の構築 ---
        # 統合ロジック: Keyがあれば抽出、無ければデータ全体を文字列化して使用
        combined_assistant_msg = ""
        if current_context_data:
            if prev_response_key and isinstance(current_context_data, dict):
                # 特定のKeyから継承データを取得
                raw_text = current_context_data.get(prev_response_key, str(current_context_data))
            else:
                # Key指定がない、または辞書でない場合はそのまま使用
                raw_text = str(current_context_data)
            
            # トークン制限を考慮してテキストを取得
            inheritance_text = _get_safe_inheritance_data(raw_text, model_name, max_inheritance_tokens)
            if inheritance_text:
                combined_assistant_msg = f"【前回の回答内容】\n{inheritance_text}"

        # --- 2. system_prompt (指示とフィードバック) の構築 ---
        skeleton = f"{prompt}\n\n"
        if format:
            skeleton += f"- [出力形式:JSONスキーマ]\n{json.dumps(format, indent=2, ensure_ascii=False)}\n"
        elif prev_response_key:
            skeleton += f"- 全体のまとめ内容を{prev_response_key}セクションを作って記述してください。\n"

        # 改善指示は User への命令(System/User側)として配置し、Assistantと分離
        if evaluation_feedback:
            skeleton += f"### 【重要：前回の回答への改善指示】\n{evaluation_feedback}\n"
            skeleton += "上記の指摘事項を必ず反映させ、前回の回答を改善・修正してください。\n\n"

        # トークン計算と制限チェック
        reserved_tokens = count_tokens(question + skeleton + prompt_data_tytle, model_name)
        context_window_limit = get_context_window_size(model_name)
        available_tokens = context_window_limit - reserved_tokens - 100
        
        if available_tokens <= overlap_tokens:
            print("ERROR: コンテキスト制限を超過しました。", file=sys.stderr)
            break

        current_chunk, consumed_text = get_chunk_by_token_limit(remaining_data, available_tokens, model_name)

        try:
            print(f"{model_name} 実行中 {iteration}回目 (残: {len(remaining_data)}文字 / 枠: {available_tokens}tokens)", file=sys.stderr)
            full_text = execute_llm_request(
                ollama_client=ollama_client,
                model_name=model_name,
                question=question,
                system_prompt=skeleton,
                prompt=prompt_data_tytle + current_chunk,
                assistant_message=combined_assistant_msg, # 過去の純粋な回答のみ
                format=format,
                stream=stream,
                use_chat=use_chat,
                options=options
            )
            print(full_text[:1000]+"\n---------------------(preview end)\n", file=sys.stderr)
            # --- 3. データの抽出と更新 ---
            if format:
                try:
                    clean_json = re.sub(r'^```json\s*|```$', '', full_text, flags=re.MULTILINE).strip()
                    res_obj = json.loads(clean_json)
                    # 次回ループ用のコンテキストを更新
                    current_context_data = res_obj 
                    answer_chunks.append(res_obj)
                except json.JSONDecodeError:
                    answer_chunks.append({"summary": "JSON解析エラー", "raw": full_text})
            else:
                current_context_data = full_text
                answer_chunks.append(full_text)

            remaining_data = remaining_data[len(consumed_text):]
            

        except Exception as e:
            print(f"ERROR: 処理失敗: {e}", file=sys.stderr)
            break
            
    return answer_chunks

def extract_dicts_with_required_keys(
    data: Union[Dict[str, Any], List[Any], Any],
    required_keys: List[str]
) -> List[Dict[str, Any]]:
    """
    データ構造を再帰的に深く探索し、指定されたすべての必須キーを持つ辞書を抽出します。
    Documentが見つかった場合、そのDocumentより下層の探索は行いません。

    Args:
        data: 現在探索中のデータ（辞書、リスト、またはその他の値）。
        required_keys (List[str]): Documentが必ず持っているべきキー名のリスト。

    Returns:
        List[Dict[str, Any]]: 抽出されたDocument辞書のリスト。
    """
    extracted_elements = []
    
    # 1. 辞書の場合の処理
    if isinstance(data, dict):
        
        # A. 現在の辞書が目的のDocumentであるかチェック
        # (例: {"name": "...", "summary": "...", ...} の形式)
        if all(key in data for key in required_keys):
            # 目的のDocumentが見つかったため、この辞書を結果に追加し、
            # この辞書以下のキー/値の探索は行わずに、ここで処理を終了して戻る
            extracted_elements.append(data)
            return extracted_elements
        
        # B. 目的のDocumentではない場合、値(Value)を再帰的に探索する
        for key, value in data.items():
            # Documentが見つかる可能性があるのは、値が辞書またはリストの場合のみ
            if isinstance(value, (dict, list)):
                # 再帰呼び出し
                found = extract_dicts_with_required_keys(value, required_keys)
                extracted_elements.extend(found)
                # 注: ここで found が空でない場合でも、他のキーも探索します。
                # なぜなら、{"sec1": {doc}, "sec2": {doc}} のように並列にDocumentが存在する可能性があるためです。

    # 2. リストの場合の処理
    elif isinstance(data, list):
        # リストの要素を順に再帰的に探索する
        for element in data:
            # Documentが見つかる可能性があるのは、要素が辞書またはリストの場合のみ
            if isinstance(element, (dict, list)):
                # 再帰呼び出し
                found = extract_dicts_with_required_keys(element, required_keys)
                extracted_elements.extend(found)
    
    # 3. その他の型 (文字列、数値など) の場合は何もしない

    return extracted_elements

    
def clean_markdown_code_block(content: str) -> str:
    """
    LLM出力で付与された不要なマークダウンコードブロックのラッパーを除去します。
    例: ```markdown ... ``` や ```json ... ```
    """
    if not content:
        return ""
        
    processed_content = content.strip()
    
    # 一般的な言語マーカーを除去
    # ```markdown, ```json, ```python, ```text, ``` などを考慮
    if processed_content.startswith("```"):
        first_line_end = processed_content.find('\n')
        if first_line_end != -1:
            # 最初の行（マーカー部分）をスキップ
            processed_content = processed_content[first_line_end:].strip()
        else:
            # 単純な ``` のみの場合
            processed_content = processed_content[3:].strip()
            
    # 最後の ``` を除去
    if processed_content.endswith("```"):
        processed_content = processed_content[:-3].strip()
        
    return processed_content

    
# =============================================================
# メイン・オーケストレーション・ロジック
# =============================================================


def split_text_by_pattern(text: str, pattern: str) -> List[str]:
    """
    指定された正規表現パターンでテキストを分割する。
    セパレータ自体（例: < 濃度送信 >）も内容のヒントとして各チャックの先頭に残す。
    """
    if not pattern:
        return [text]
    
    # パターンにグループ括弧 () を含めることで、split結果にセパレータ自体も含まれるようにする
    # 例: r'(<[^>]+>)' 
    regex = re.compile(f"({pattern})")
    parts = regex.split(text)
    
    chunks = []
    current_chunk = ""
    
    # splitの結果は [空, セパレータ1, 内容1, セパレータ2, 内容2...] のようになる
    for part in parts:
        if not part.strip():
            continue
        if regex.match(part):
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = part # セパレータを保持
        else:
            current_chunk += "\n" + part
            
    if current_chunk:
        chunks.append(current_chunk.strip())
        
    return chunks
