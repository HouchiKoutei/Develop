import re
import sys
import json 
from datetime import datetime
from typing import Tuple, List, Dict, Any, Optional, Union
import os 
import time

# --------------------------------------------------------------------
# ⚠️ 注意: 実行環境に合わせてパスとインポートを調整してください
# --------------------------------------------------------------------
source_directory = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(source_directory, "..", ".."))
sys.path.insert(0, project_root)

# LLM_Control.py と KeyManager.py から必要な関数や設定をインポート
from Sources.Common import LLM_Control 
from Sources.Common import DictionaryControl
from Sources.Common import FileControl 

# ====================================================================
# I. データ構造定義 (Content Document Schema)
# --------------------------------------------------------------------

# 評価結果のサブ構造
EvaluationResult = Dict[str, Union[int, float, str]]

# ContentDocument の基本構造
ContentDocument = Dict[str, Any] 

# 評価用モデルに与えるプロンプトのテンプレート (大域変数)
EVALUATION_PROMPT_AND_TIME_TEMPLATE = """
以下の「ユーザーの質問」に対する「モデルの回答」を読み、その**正確性、包括性、明確さ**を評価してください。
また、その回答が生成されるまでにかかった時間（{latency:.2f}秒）も考慮に入れ、**最終的な点数（1点から100点）**を付けてください。

* **高得点の基準**: 正確で明確な回答。要約元が長文の場合があるため、内容が充実していれば文章が長いこと自体は減点ではない。生成時間が短い(例:1000文字で30秒未満)。
* **低得点の基準**: 情報が不正確または不明瞭、同じ情報が繰返し重複している、もしくは回答生成に極端に時間がかかった（例：1000文字で120秒以上）。

点数のみを**<SCORE>X</SCORE>**という形式で出力してください。また、回答全体についての**総評**を、必ず**<SUMMARY>総評テキスト</SUMMARY>**という形式で、点数の後に続けて記述してください。点数と総評以外のテキストは一切含めないでください。

---
ユーザーの質問: {question}
---
モデルの回答: {answer}
---
生成時間: {latency:.2f}秒
"""
# 評価用モデルに与えるプロンプトのテンプレート (大域変数)
EVALUATION_PROMPT_TEMPLATE = """
以下の「ユーザーの質問」に対する「モデルの回答」を読み、その**正確性、包括性、明確さ**を評価してください。
**最終的な点数（1点から100点）**を付けてください。
* **高得点の基準**: 正確で明確な回答。情報が詳細で多岐に渡っている。要約元が長文の場合があるため、内容が充実していれば文章が長いこと自体は減点ではない。
* **低得点の基準**: 情報が不正確または不明瞭。同じ情報が繰返し重複している。

点数のみを**<SCORE>X</SCORE>**という形式で出力してください。また、回答全体についての**総評**を、必ず**<SUMMARY>総評テキスト</SUMMARY>**という形式で、点数の後に続けて記述してください。点数と総評以外のテキストは一切含めないでください。

---
ユーザーの質問: {question}
---
モデルの回答: {answer}
"""

def parse_evaluation_output(response_text: str) -> Tuple[int, str]:
    """
    評価用モデルのテキスト出力からスコアと総評を抽出します。（純粋関数）
    """
    score_match = re.search(r"<SCORE>(\d+)</SCORE>", response_text)
    score = int(score_match.group(1)) if score_match else 0
    summary_match = re.search(r"<SUMMARY>(.*?)</SUMMARY>", response_text, re.DOTALL)
    summary = summary_match.group(1).strip() if summary_match else ""
    return score, summary

def format_ranking_output(
    question: str, 
    evaluation: str, 
    evaluated_documents: List[ContentDocument]
) -> str:
    """
    評価済みContentDocumentを直接ソートし、ランキング形式のテキストを生成します。
    回答部分は、除外キー以外のstr型の項目をすべて抽出します。
    """
    
    if not evaluated_documents:
        return ""

    # 1. documentのままスコアで降順ソート
    sorted_docs = sorted(
        evaluated_documents,
        key=lambda d: d.get('evaluation', {}).get('score', 0) 
                      if isinstance(d.get('evaluation', {}).get('score'), (int, float)) else 0,
        reverse=True
    )
    
    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    exclude_keys = {'generation_information', 'source_info', 'evaluation', 'source_paths', 'category', 'model_name'}

    # ヘッダ部分
    output = f"--- モデル評価結果 ({timestamp_str}) ---\n"
    output += f"【ユーザーの質問】: {question}\n"
    output += f"【評価に使用したモデル】: {evaluation}\n\n"

    # 2. ソートされたDocumentから直接テキストを生成
    for i, doc in enumerate(sorted_docs, start=1):
        generation_information = doc.get('generation_information', {})
        evaluation = doc.get('evaluation', {})
        
        # 基本情報の取得
        model_name = generation_information.get('model', 'N/A')
        score_val = evaluation.get('score', 0)
        score_display = f"{score_val}点" if isinstance(score_val, (int, float)) else str(score_val)
        latency =  generation_information.get('latency', 0.0)
        
        # --- 回答セクション: 特定キーを除外 & str型のみ抽出 ---
        answer_parts = []
        for key, value in doc.items():
            if key not in exclude_keys and isinstance(value, str) and value:
                answer_parts.append(f"[{key}]\n{value}")
        
        answer_text = "\n".join(answer_parts)
        # --------------------------------------------------

        output += f"--------------------------------------\n"
        output += f"#{str(i)} {model_name} ({doc.get('category', 'N/A')})\n"
        output += f"🎯 スコア: {score_display}\n"
        output += f"⏱ 生成時間: {latency:.2f}秒\n"
        
        # ソースパスの表示
        source_paths = doc.get('source_paths', [])
        source_names = ", ".join([os.path.basename(p) for p in source_paths])
        output += f"🔗 ソース: {source_names}\n"
        
        # 総評と動的に抽出された回答
        output += f"📝 総評:\n{evaluation.get('summary', '')}\n" 
        output += f"🧾 回答:\n{answer_text}\n" 
    
    output += "\n================================================================================\n"
    return output


# ====================================================================
# I. 純粋関数：評価ロジック
# ====================================================================

def evaluate_text_content(
    target_text: str,
    question: str,
    evaluation_model: str,
    ollama_client: Any,
    latency: float = 0.0,
    evaluate_template: str = EVALUATION_PROMPT_TEMPLATE
) -> Tuple[int, str]:
    """
    純粋なテキスト内容をLLMで評価し、(スコア, 総評)を返します。
    Document構造に依存しないため、リトライループ内でも利用可能です。
    """
    prompt = evaluate_template.format(question=question, answer=target_text, latency=latency)
    
    response_text = LLM_Control.execute_llm_request(
        ollama_client=ollama_client,
        model_name=evaluation_model,
        question="以下の回答を評価してください。",
        prompt=prompt,
        system_prompt="あなたは厳格な採点官です。",
        use_chat=True,
        options={'temperature': 0.1}
    )
    
    return parse_evaluation_output(response_text)
def format_and_save_ranking(
    question: str, 
    evaluation_model: str, 
    evaluated_documents: List[Dict[str, Any]],
    output_file_path: str=""
) -> str:
    """
    評価済みドキュメントをソートし、ランキングを作成してファイルに保存する。
    """
    if not evaluated_documents:
        return ""

    # 1. スコアで降順ソート
    sorted_docs = sorted(
        evaluated_documents,
        key=lambda d: d.get('evaluation', {}).get('score', 0),
        reverse=True
    )
    
    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 2. テキスト構成 (Header)
    output = f"--- モデル評価結果 ({timestamp_str}) ---\n"
    output += f"【ユーザーの質問】: {question}\n"
    output += f"【評価に使用したモデル】: {evaluation_model}\n\n"

    # 3. 各回答の抽出
    for i, doc in enumerate(sorted_docs, start=1):
        generation_information = doc.get('generation_information', {})
        eval_data = doc.get('evaluation', {})
        
        model_name = generation_information.get('model', 'N/A')
        score = eval_data.get('score', 0)
        latency = generation_information.get('latency', 0.0)
        source_name = doc.get('source_name', 'N/A')
        
        answer_text = DictionaryControl.format_to_text(doc)
        output += f"--------------------------------------\n"
        output += f"#{i} {model_name} ({source_name}) | 🎯 スコア: {score}点 | ⏱ {latency:.2f}s\n"
        output += f"📝 総評: {eval_data.get('summary', '')}\n"
        output += f"🧾 回答:\n{answer_text}\n"

    # 4. ファイル出力
    if output_file_path:
        FileControl.write_file(output_file_path, output, append=False)
    
    return output

# ====================================================================
# 生成 + 自己改善リトライロジック
# ====================================================================

def execute_llm_request_with_retry(
    ollama_client: Any,
    model_name: str,
    evaluation_model: str,
    question: str,
    prompt: str = "",
    target_score: int = 80,
    max_retries: int = 3,
    **kwargs
) -> Tuple[str, Dict[str, Any]]:
    """
    回答生成後、目標スコアに達するまで改善を繰り返す。
    """
    current_feedback = ""
    attempt = 0
    
    while attempt <= max_retries:
        # フィードバックがある場合は指示を追加
        full_prompt = prompt
        if current_feedback:
            full_prompt += f"\n\n【改善指示】:\n{current_feedback}"

        answer = LLM_Control.execute_llm_request(
            ollama_client=ollama_client,
            model_name=model_name,
            question=question, # エラー修正: 必須引数を渡す
            prompt=full_prompt,
            **kwargs
        )

        score, summary = evaluate_text_content(
            target_text=answer,
            question=question,
            evaluation_model=evaluation_model,
            ollama_client=ollama_client
        )

        print(f"  [Attempt {attempt}] {model_name}: {score}点", file=sys.stderr)

        if score >= target_score:
            break
        
        current_feedback = f"前回のスコアは{score}点でした。総評: {summary}\nこれらを反映して回答を修正してください。"
        attempt += 1

    return answer, {"score": score, "summary": summary, "evaluator": evaluation_model, "attempts": attempt}