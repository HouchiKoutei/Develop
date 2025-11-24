import ollama
import re
import sys
from datetime import datetime
from typing import Tuple, List, Dict, Any

import LLM_Control
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
        "Ollama_server_url":OLLAMA_SERVER_URL,
        "rag_server_url":"http://192.168.40.72:8001",
        "rag_files": ["./Sources/Tests/LLM_Control.py","./Sources/Tests/LLM_Evaluate.py" ],
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

def generate_evaluation(
    evaluator_model: str, 
    question: str, 
    answer: str, 
    latency: float, 
    client: Any,
    prompt_template: str = EVALUATION_PROMPT_TEMPLATE # ★★★ デフォルト値として大域変数を保持 ★★★
) -> Tuple[int, str]:
    """評価用モデルを使用して回答をスコアリングし、総評を生成します。"""
    
    if not LLM_Control._pull_model_if_not_exists(evaluator_model, client):
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
# LLM_Control.py から移動し、評価機能の中心としてここに残します。
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
                ollama_server_url_memory = ollama_server_url
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
        current_rag_server_url = task.get('rag_server_url', rag_server_url_setting)
        current_rag_template = task.get('rag_prompt', LLM_Control.RAG_PROMPT_TEMPLATE if use_rag else "") # RAG無効時は空
        current_evaluation_prompt = task.get('evaluation_prompt', EVALUATION_PROMPT_TEMPLATE)

        # 2. RAGの準備 (ファイルがあればFastAPIサーバーに登録)
        rag_db_status = False 
        if use_rag and rag_files:
            rag_db_status = LLM_Control.load_files_to_vector_db(rag_files, ollama_client, current_rag_server_url)

        evaluation_results = []

        # 3. 候補モデルの回答生成と時間計測 (RAGモードで実行)
        for model_name in candidate_models:
            
            # RAG/非RAG の実行フラグを決定
            # RAGが有効だがDB登録に失敗した場合は、非RAGで実行する
            is_rag_run = use_rag and rag_db_status
            
            # ★★★ 修正: モデル名にRAG状態を付加して結果を区別する ★★★
            model_label = f"{model_name}{' (RAG)' if is_rag_run else ' (Non-RAG)'}"

            answer, latency = LLM_Control.generate_response(
                model_name, 
                question, 
                ollama_client, 
                is_rag_run, # RAG DB登録が成功した場合のみTrue
                current_rag_template,
                current_rag_server_url
            )
            
            result_data = {
                'model': model_label, # RAG状態を反映したモデル名
                'answer': answer,
                'latency': latency,
                'score': 0,
                'summary': "未評価"
            }
            
            # 4. 評価用モデルによるスコアリングと総評の生成
            if not answer.startswith("[エラー:"):
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
                
        # 5. ランキングテキストを作成
        ranking_text = format_ranking_output(question, current_evaluator_model, evaluation_results)
        
        # 6. 結果をファイルに追記保存
        LLM_Control._write_result_to_file(file_path, ranking_text)
            
    print("--- 全てのタスクが完了しました ---")

if __name__ == "__main__":
    print("Ollamaモデル評価＆ランキングプログラムを開始します...")
    
    # 1. Ollamaサーバーの起動確認と起動
    LLM_Control._start_ollama_server() 
    
    # 2. タスクの実行
    llm_evaluate(tasks, OLLAMA_SERVER_URL,RAG_SERVER_URL)