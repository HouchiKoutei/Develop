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
# --- 設定 ---
tasks = [
    {
        "text": "地球のコアは何で構成されていますか？",
        "model": ["llama3.1:8b", "gemma2:9b", "qwen2:7b"], 
        "evaluator_model": "llama3.1:8b", 
        "file_path": "result.log",
        "use_rag": True, 
        "Ollama_server_url":"http://127.0.0.1:11434",
        "rag_server_url":"http://192.168.40.72:8001",
        "rag_files": "" ,
        "rag_prompt": """
            以下のソースコードの内容のみに基づいて、「質問」に回答してください。
            ソースコードに記載されていない内容については回答しないでください。

            ---
            ソースコード:
            {context}
            ---
            質問: {question}
        """

    },
    {
        "text": "AutoClickプロジェクトのkivy_ui_parts.pyの役割を説明してください。",
        "model": ["llama3.1:8b","gemma2:9b"],
        "evaluator_model": "llama3.1:8b",
        "file_path": "result.log",
        "evaluator_model": "gemma2:9b"
    }
]

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

# 評価用モデルに与えるプロンプトのテンプレート (大域変数)
EVALUATION_PROMPT_TEMPLATE = """
以下の「ユーザーの質問」に対する「モデルの回答」を読み、その**正確性、包括性、明確さ**を評価してください。
また、その回答が生成されるまでにかかった時間（{latency:.2f}秒）も考慮に入れ、**最終的な点数（1点から100点）**を付けてください。

* **高得点の基準**: 正確で明確な回答であり、かつ生成時間が短い（例：3秒未満）。
* **低得点の基準**: 情報が不正確または不明瞭、もしくは回答生成に極端に時間がかかった（例：30秒以上）。

点数のみを**<SCORE>X</SCORE>**という形式で出力してください。また、回答全体についての**総評**を、必ず**<SUMMARY>総評テキスト</SUMMARY>**という形式で、点数の後に続けて記述してください。点数と総評以外のテキストは一切含めないでください。

---
ユーザーの質問: {question}
---
モデルの回答: {answer}
---
生成時間: {latency:.2f}秒
"""

# ====================================================================
# I/O関数 (副作用あり)
# ====================================================================

# ★★★ 修正点1-A: サーバー準備完了を指数関数的バックオフでポーリングするヘルパー関数を追加 ★★★
def _wait_for_ollama_ready(host_url: str = "http://127.0.0.1:11434", max_retries: int = 10, initial_delay: int = 2):
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
            _wait_for_ollama_ready("http://127.0.0.1:11434")
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

def generate_evaluation(
    evaluator_model: str, 
    question: str, 
    answer: str, 
    latency: float, 
    client: Any,
    prompt_template: str = EVALUATION_PROMPT_TEMPLATE # ★★★ デフォルト値として大域変数を保持 ★★★
) -> Tuple[int, str]:
    """評価用モデルを使用して回答をスコアリングし、総評を生成します。"""
    
    if not _pull_model_if_not_exists(evaluator_model, client):
        print(f"評価モデル '{evaluator_model}' が利用できません。スコアリングをスキップします。")
        return 0, "評価モデルが利用できません。"

    # 外部から渡されたテンプレートを使用
    prompt = prompt_template.format(question=question, answer=answer, latency=latency)
    
    try:
        print(f"評価用モデル '{evaluator_model}' でスコアリング中...")
        
        response_text = client.generate(
            model=evaluator_model,
            prompt=prompt,
            stream=False,
            options={'temperature': 0.1}
        )['response'].strip()

        return parse_evaluation_output(response_text)

    except Exception as e:
        print(f"エラー: 評価モデル '{evaluator_model}' の実行中にエラーが発生しました: {e}")
        return 0, f"評価モデル実行エラー: {e}"

# ====================================================================
# 純粋関数 (データ変換)
# ====================================================================

def parse_evaluation_output(response_text: str) -> Tuple[int, str]:
    """
    評価用モデルのテキスト出力からスコアと総評を抽出します。
    """
    # スコア抽出: <SCORE>X</SCORE>
    score_match = re.search(r"<SCORE>(\d+)</SCORE>", response_text)
    score = int(score_match.group(1)) if score_match else 0

    # 総評抽出: <SUMMARY>総評テキスト</SUMMARY> 
    summary_match = re.search(r"<SUMMARY>(.*?)</SUMMARY>", response_text, re.DOTALL)
    summary = summary_match.group(1).strip() if summary_match else "総評の抽出に失敗しました。"
    
    return score, summary

def format_ranking_output(question: str, evaluator: str, results: List[Dict[str, Any]]) -> str:
    """
    モデル評価結果のリストから、ランキング形式のテキストを生成します。
    """
    # スコアに基づいて降順にソート
    sorted_results = sorted(results, key=lambda x: x.get('score', 0), reverse=True)
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ランキングテキストの構築
    ranking_output = f"--- モデル評価結果 ({timestamp}) ---\n"
    ranking_output += f"【ユーザーの質問】: {question}\n"
    ranking_output += f"【評価に使用したモデル】: {evaluator}\n\n"
    ranking_output += "【評価結果ランキング】:\n"
    
    for i, result in enumerate(sorted_results):
        ranking_output += f"  {i+1}. モデル: {result['model']} - **スコア: {result['score']}点** (生成時間: {result['latency']:.2f}秒)\n"
        ranking_output += f"     [総評]: {result['summary']}\n"
        ranking_output += f"     [回答の抜粋]: {result['answer'][:100]}...\n\n"

    ranking_output += "--- 詳細 --- \n"
    for result in sorted_results:
         ranking_output += f"モデル: {result['model']}\n"
         ranking_output += f"スコア: {result['score']}点\n"
         ranking_output += f"生成時間: {result['latency']:.2f}秒\n"
         ranking_output += f"総評:\n{result['summary']}\n"
         ranking_output += f"回答:\n{result['answer']}\n"
         ranking_output += "--------------------------------------\n"
         
    return ranking_output

# ====================================================================
# メインのオーケストレーション関数 (設定の取得ロジックを追加)
# ====================================================================

def llm_evaluate(
    tasks: List[Dict[str, Any]], 
    ollama_server_url_setting: str = OLLAMA_SERVER_URL,  
    rag_server_url_setting: Any = RAG_SERVER_URL
):
    """
    定義された評価タスクを順番に実行するメイン関数。RAGサーバー対応。
    """
    
    ollama_server_url_memory = ""
    for i, task in enumerate(tasks):
        try:
            ollama_server_url = task.get('ollama_server_url', ollama_server_url_setting)
            if ollama_server_url!= ollama_server_url_memory:
                ollama_client = ollama.Client(host=ollama_server_url)
                print(f"Ollamaクライアントを {ollama_server_url} に接続しました。")
                ollama_server_url = ollama_server_url
        except Exception as e:
            print(f"エラー: Ollamaクライアントの初期化に失敗しました: {e}", file=sys.stderr)
            return # 失敗した場合は終了

        print(f"--- タスク {i+1}/{len(tasks)} を開始 ---")
        question = task['text']
        candidate_models = task['model']
        evaluator_model = task['evaluator_model']
        file_path = task['file_path']
        use_rag = task.get('use_rag', False)
        rag_files = task.get('rag_files',)

        # 1. 各設定項目の取得 (タスク固有 > 引数/大域変数)
        current_evaluator_model = task.get('evaluation', evaluator_model)
        # ★★★ タスクにURLが設定されていない場合、引数の rag_server_host を使用 ★★★
        current_rag_server_url = task.get('rag_server_url', rag_server_url_setting)
        current_rag_template = task.get('rag_prompt', RAG_PROMPT_TEMPLATE)
        current_evaluation_prompt = task.get('evaluation_prompt', EVALUATION_PROMPT_TEMPLATE)

        db_status = False 
        
        # 0. RAGの準備 (ファイルがあればFastAPIサーバーに登録)
        if use_rag and rag_files:
            # ★★★ 生成したクライアントインスタンスを渡す ★★★
            db_status = load_files_to_vector_db(rag_files, ollama_client, current_rag_server_url)

        evaluation_results = []

        # 1. 候補モデルの回答生成と時間計測
        for model_name in candidate_models:
            # ★★★ タスク固有の設定を渡す ★★★
            answer, latency = generate_response(
                model_name, 
                question, 
                ollama_client, 
                db_status, 
                current_rag_template,
                current_rag_server_url
            )
            
            result_data = {
                'model': model_name,
                'answer': answer,
                'latency': latency,
                'score': 0,
                'summary': "未評価"
            }
            
            # 2. 評価用モデルによるスコアリングと総評の生成
            if not answer.startswith("[エラー:"):
                # ★★★ タスク固有の評価モデルとプロンプトを渡す ★★★
                score, summary = generate_evaluation(
                    current_evaluator_model, 
                    question, 
                    answer, 
                    latency, 
                    ollama_client, 
                    current_evaluation_prompt
                )
                result_data['score'] = score
                result_data['summary'] = summary
            else:
                 result_data['summary'] = "回答生成エラーのため評価スキップ。"
                
            evaluation_results.append(result_data)
                
        # 3. ランキングテキストを作成
        ranking_text = format_ranking_output(question, current_evaluator_model, evaluation_results)
        
        # 4. 結果をファイルに追記保存
        _write_result_to_file(file_path, ranking_text)
            
    print("--- 全てのタスクが完了しました ---")

if __name__ == "__main__":
    print("Ollamaモデル評価＆ランキングプログラムを開始します...")
    
    # 1. Ollamaサーバーの起動確認と起動
    _start_ollama_server() 
    
   
    
    
    # 2. タスクの実行
    llm_evaluate(tasks, OLLAMA_SERVER_URL,RAG_SERVER_URL)