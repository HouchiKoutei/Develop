import ollama
import json
import os
import sys
import time
import shutil
import re
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
import datetime
import gc

# --- パス設定 ---
source_directory = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(source_directory, "..", ".."))
sys.path.insert(0, project_root)

from Sources.Common import LLM_Control 
from Sources.Common import LLM_Evaluate
from Sources.Common import FileControl
from Sources.Common import DictionaryControl


DOCUMENT_SCHEMA = {
    "type": "object",
    "required": ["name", "category", "summary"],
    "properties": {
        "name": {
            "type": "string",
            "minLength": 1,
            "description": "AIモデルが文書の内容に基づいて推奨する、具体的で簡潔なName。"
        },
        "category": {
            "type": "string",
            "description": "AIモデルが文書の性質を分析して推奨する、論理的な分類（Category）。例: Research, Memo, Specification, Source Code, Function Definitionなど。"
        },
        "summary": {
            "type": "string",
            "description": "AIモデルによる要約"
        },
        "source_paths": {
            "type": "array",
            "items": { "type": "string" },
            "default": []
        },
        "generation_information": {
            "type": "object",
            "properties": { 
                "model_info": {"type": "string"},
                "timestamp": {"type": "string", "description": "yyyy/mm/dd hh/mm/ss"},
                "latency": {"type": ["number", "null"], "minimum": 0}
            },
            "required": ["model_info", "timestamp"],
            "additionalProperties": False
        },
        "evaluation": {
            "type": "object",
            "properties": { 
                "score": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
                "comment": {"type": ["string", "null"]}
            },
            "additionalProperties": False
        }
    },
    "additionalProperties": False
} 
MIN_DOCUMENT_SCHEMA = {
    "type": "object",
    "required": ["name", "category", "summary","overview"],
    "properties": {
        "name": {
            "type": "string",
            "minLength": 1,
            "description": "AIモデルが文書の内容に基づいて推奨する、具体的で簡潔なName。"
        },
        "category": {
            "type": "string",
            "description": "AIモデルが文書の性質を分析して推奨する、論理的な分類（Category）。例: Research, Memo, Specification, Source Code, Function Definitionなど。"
        },
        "summary": {
            "type": "string",
            "description": "AIモデルによる要約"
        },
        "overview": {
        "description": "AIモデルによる全体像のまとめ(mermaid記法)",
        "title": "overview",
        "type": "string"
        }
    },
    "additionalProperties": False

}
DOCUMENT_LIST_SCHEMA = {
  "title": "Root Array Document List Schema",
  "type": "array",
  "description": "AIモデルから抽出されたDocumentオブジェクトの配列（リスト）をルートとするスキーマ。",
  "items": {
    "additionalProperties": False,
    "description": "抽出される個々のDocumentのデータ構造を定義します。",
    "properties": {
      "name": {
        "description": "AIモデルが文書の内容に基づいて推奨する、具体的で簡潔なName。",
        "minLength": 1,
        "title": "Name",
        "type": "string"
      },
      "category": {
        "description": "AIモデルが文書の性質を分析して推奨する、論理的な分類（Category）。例: Research, Memo, Specification, Source Code, Function Definitionなど。",
        "title": "Category",
        "type": "string"
      },
      "summary": {
        "description": "AIモデルによる要約",
        "title": "Summary",
        "type": "string"
      },
      "overview": {
        "description": "AIモデルによる全体像のまとめ(mermaid記法)",
        "title": "overview",
        "type": "string"
      }
    },
    "required": [
      "name",
      "category",
      "summary",
      "overview"
    ],
    "title": "DocumentModel",
    "type": "object"
  }
}
# --------------------------------------------------------------------------------

ContentDocument = Dict[str, Any]

def create_content_document(
    name: str,
    category: str, # 'answer', 'evaluation_result', 'file_summary', 'final_analysis' など
    summary: Union[str, Dict[str, Any]], # 文字列またはJSONデータ
    model_name: str,
    latency: float,
    generation_information: Dict[str, Any],
    source_paths: Optional[List[str]] = None,
    file_path: Optional[str] = None,
    evaluation_result: Optional[Dict[str, Union[int, float, str]]] = None,
) -> ContentDocument:
    """
    指定されたパラメータに基づき、ContentDocumentを構築します。
    """
    
    generation_information = {
        "model_info": model_name,
        "timestamp": datetime.now().isoformat(),  
        "latency": latency,                      
        **generation_information                    
    }
    
    # 不要なキーを削除
    generation_information.pop('model', None)
    generation_information.pop('evaluation_model', None)
    
    document: ContentDocument = {
        "name": name,
        "category": category,
        "summary": summary,
        "source_paths": source_paths if source_paths is not None else [],
        "file_path": file_path, # 最終的な保存先
        "evaluation": evaluation_result,
        "generation_information": generation_information
    }
    
    return document
def create_document_list(
    question: str,
    source_texts: List[str],
    model_name: str,
    ollama_client: Any,
    evaluation_model: str = "",
    evaluate_template: str = LLM_Evaluate.EVALUATION_PROMPT_TEMPLATE,
    target_score: int = 85,
    max_retry: int = 3,
    prev_response: str = "",
    prev_response_key: str = None,

    format: Optional[Dict[str, Any]] = "",
    options: Optional[Dict[str, Any]] = {'temperature': 0.2}
) -> List[Dict[str, Any]]:
    all_results = []
    for text in source_texts:
        retry = 0
        current_prev_response = prev_response
        feedback = ""
        best_doc = None
        max_score_found = -1

        while retry < max_retry:
            start_time = time.time()
            retry += 1
            print(f"  [Try {retry}] {model_name} で処理中...", file=sys.stderr)

            # --- 1. 生成処理 ---
            responses = LLM_Control.answer_question(
                question=question,
                data_source=text,
                model_name=model_name,
                ollama_client=ollama_client,
                prev_response=current_prev_response,
                prev_response_key=prev_response_key,
                evaluation_feedback=feedback,
                format=format,
                options=options
            )
            generated_content = "\n".join([str(r) for r in responses]) if isinstance(responses, list) else str(responses)
            if not generated_content:
                break

            # --- 2. 評価プロセス ---
            current_result_doc = {
                "content": generated_content,
                "generation_information": {
                    "model": model_name,
                    "retrys": retry
                }
            }
            score = 0
            if evaluation_model:
                score, summary = LLM_Evaluate.evaluate_text_content(
                    target_text=generated_content,
                    question=question,
                    evaluation_model=evaluation_model,
                    ollama_client=ollama_client,
                    evaluate_template=evaluate_template
                )
                print(f"    -> 評価スコア: {score} (目標: {target_score})", file=sys.stderr)
                
                # 判定が行われた場合のみ evaluation 要素を追加
                current_result_doc["evaluation"] = {
                    "score": score,
                    "summary": summary
                }
                # generation_informationにもスコアを記録
                current_result_doc["generation_information"]["score"] = score
                current_result_doc["generation_information"]["latency"] = time.time() - start_time

            # --- 3. 最高スコアの更新 ---
            if best_doc is None or score > max_score_found:
                max_score_found = score
                best_doc = current_result_doc

            # --- 4. 終了判定 ---
            if evaluation_model and score < target_score:
                print(f"    ⚠️ スコア不足。改善リトライへ。", file=sys.stderr)
                current_prev_response = generated_content
                feedback = summary if 'summary' in locals() else ""
            else:
                break

        # 最も良かった結果をリストに追加
        if best_doc:
            all_results.append(best_doc)

    return all_results

class ContentDocument(Dict[str, Any]):
    pass


def create_multisource_document_list(task: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    ソースの収集、AI処理、ファイル出力を順次実行し、
    最終的に評価用のドキュメントリストを返す統合関数。
    """
    # --- パラメータ抽出 ---
    question = task.get("text", task.get("question", ""))
    models = task.get("model", [])
    if not isinstance(models, list): models = [models]
    
    output_path = task.get("auto_doc_output_folder", "./DocumentAuto/Analysis/")
    ranking_output_file_path = task.get("ranking_output_file_path", "./DocumentAuto/ranking.md")
    existing_mode = task.get("existing_file_mode", "skip") 
    evaluation_model = task.get("evaluation_model", "")
    integrate_model = task.get("integrate_model", "")
    target_paths = FileControl.get_file_path_list(task.get("target_paths", []), recursive=True)
    prev_response_key = task.get("prev_response_key", "summary")
    
    ollama_client = LLM_Control.initialize_ollama_client(task.get("Ollama_server_url", LLM_Control.OLLAMA_SERVER_URL))

    source_configs = []
    if task.get("use_rag"):
        source_configs.append({"type": "rag", "name": "RAG_Vector_DB"})
    if task.get("use_internet_search"):
        source_configs.append({"type": "internet", "name": "Web_Search"})
    for path in target_paths:
        if os.path.exists(path):
            source_configs.append({"type": "file", "name": os.path.basename(path), "path": path})

    final_all_documents = []
    os.makedirs(output_path, exist_ok=True)

    for config in source_configs:
        source_name = config["name"]
        source_type = config["type"]
        safe_source_name = re.sub(r'[\\/:*?"<>|]', "_", source_name).strip("_")

        try:
            # --- A. コンテンツの取得 ---
            if source_type == "rag":
                rag_files = task.get("rag_register_paths", [])
                rag_url = task.get("rag_server_url", LLM_Control.RAG_SERVER_URL)
                db_status = LLM_Control.rag_server_register(rag_files, rag_url)
                source_content = LLM_Control.rag_server_query_context(question, rag_url)
            elif source_type == "internet":
                source_content = LLM_Control.get_or_fetch_search_context(
                    question, task.get("encrypted_secrets_path"), LLM_Control.INTERNET_CACHE_FILE
                )
            
            elif source_type == "file":
                source_content = FileControl.read_file(config["path"])

            if not source_content: continue

            # --- B. モデル毎のループ ---
            for model in models:
                safe_model_name = re.sub(r'[\\/:*?"<>|]', "_", model)
                save_file_path = os.path.join(output_path, f"{safe_source_name}_{safe_model_name}.txt")

                prev_response_content = None
                skip_generate = False
                # 1. 既存ファイル/新規生成の切り分け
                if os.path.exists(save_file_path) :
                    prev_response_content = FileControl.read_file(save_file_path)
                    if existing_mode == "skip":
                        skip_generate = True

                # 2. 評価の実行 (モデルがある場合のみ)
                prev_score = -1
                feedback = ""
                if evaluation_model and prev_response_content:
                    print(f" >> 評価実行中 ({evaluation_model})...", file=sys.stderr)
                    prev_score, feedback = LLM_Evaluate.evaluate_text_content(
                        target_text=prev_response_content,
                        question=question,
                        evaluation_model=evaluation_model,
                        ollama_client=ollama_client
                    )
                
                # --- C. AIによる生成処理 (既存ファイルを prev_response として渡す) ---
                if  not skip_generate:
                    print(f" -> AI処理開始 ({model})", file=sys.stderr)
                    generated_docs = create_document_list(
                        question=question,
                        source_texts=[source_content], 
                        model_name=model,
                        ollama_client=ollama_client,
                        evaluation_model=evaluation_model,
                        target_score=task.get("target_score", 85),
                        prev_response=prev_response_content,
                        prev_response_key=prev_response_key,
                        format=task.get("format")
                    )
                else:
                    generated_docs = [
                        {
                        "content": prev_response_content,
                        "evaluation": {"score": prev_score, "summary": feedback} if evaluation_model else None,
                        "generation_information": {"model": model, "score": max(0, prev_score)}
                        }
                    ]

                # --- C. 保存処理 ---
                if not skip_generate:
                    for d in generated_docs:
                        d["source_name"] = source_name
                        # 保存テキスト構築
                        current_score = d.get("evaluation", {}).get("score", 0) if d.get("evaluation") else 0
                        content_body = DictionaryControl.format_to_text(d)
                        
                        # 既存よりスコアが高い、または新規保存の場合のみ書き込み
                        if current_score >= prev_score:
                            FileControl.write_file(save_file_path, content_body)
                        else:
                            # スコアが低い場合の保存処理（オプション）
                            low_score_path = task.get("low_score_output_folder", "")
                            if low_score_path:
                                now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                low_score_filename = f"{now_str}_{safe_source_name}_{safe_model_name}.txt"
                                low_score_full_path = os.path.join(low_score_path, low_score_filename)
                                FileControl.write_file(low_score_full_path, low_score_full_path)
                                print(f"    >> スコア未更新のため別フォルダに保存: {low_score_full_path}", file=sys.stderr)
                            else:
                                print(f"    >> 生成完了（スコア {current_score} は既存 {prev_score} 以下につきファイル更新なし）", file=sys.stderr)                    
                final_all_documents.extend(generated_docs)
                gc.collect()

        except Exception as e:
            print(f" ❌ エラー: {e}", file=sys.stderr)

    # --- C. ランキング出力 (evaluation) ---
    if evaluation_model and len(final_all_documents) > 1 and ranking_output_file_path:
        LLM_Evaluate.format_and_save_ranking(
            question = question,
            evaluation_model = evaluation_model,
            evaluated_documents = final_all_documents,
            output_file_path = ranking_output_file_path
        )
    # --- D. 最終統合 (Integrate) ---
    if integrate_model and final_all_documents:
        print(f"\n[Step] {integrate_model} による最終統合...", file=sys.stderr)
        final_report = integrate_document_list(question, final_all_documents, integrate_model, ollama_client)
        report_path = task.get("integrate_file_path", os.path.join(output_path, "Final_Integrated_Report.md"))
        FileControl.write_file(report_path, final_report)

    return final_all_documents
# --------------------------------------------------------------------------------
# 3. 構成要素の統合関数: integrate_document_list (修正版: JSONではなく単一のstrを返す)
# --------------------------------------------------------------------------------
def integrate_document_list(
    question: str,
    document_list: List[Dict[str, Any]],
    model_name: str,
    ollama_client: Any,
    options: Optional[Dict[str, Any]] = {'temperature': 0.2}
) -> str:
    """
    answer_questionを活用し、DocumentListをトークン制限に応じて自動分割・統合して
    最終的なテキストレポートを生成します。
    """

    # 1. DocumentListを一つの大きなJSON文字列に変換
    # (answer_question側で適切なサイズに分割されるため、ここでは一括で結合して渡す)
    document_source_text = json.dumps(document_list, ensure_ascii=False, indent=2)

    # 2. システム指示と統合用質問の構築
    # answer_question内のPROMPT_SKELETONと合流することを考慮した指示にします
    combined_question = (
        f"以下の[参照データ]（DocumentList）の内容をすべて把握し、統合してください。\n"
        f"その上で、ユーザーの質問：'{question}' に対して、詳細かつ一貫した最終レポートを生成してください。\n"
        f"※注意事項: JSON形式ではなく、プレーンな文章で出力してください。"
    )

    print(f"INFO: Document統合開始。Document数: {len(document_list)}。自動分割処理を実行します...", file=sys.stderr)

    # 3. answer_questionを呼び出してチャンクごとの回答を得る
    # この関数内でトークン計算・分割・LLM呼び出しがすべて完結します
    responses = LLM_Control.answer_question(
        question = combined_question,
        data_source = document_source_text,
        model_name = model_name,
        ollama_client = ollama_client,
        format = None,   # テキストレポートとして出力させるためNone
        stream = False,
        options = options
    )

    # 4. 全応答の統合
    if not responses or all("FATAL ERROR" in r for r in responses):
        return "ERROR: Document統合による最終レポートを生成できませんでした。"

    # チャンクごとに生成された文章を結合
    # 各チャンクが独立した要約になっている可能性があるため、境界を明確にして結合します
    final_report = "\n\n--- [セクション統合] ---\n\n".join(responses)

    return final_report

def _create_document_path(doc: Dict[str, Any], doc_root: str) -> Path:
    """
    Documentの内容（name, category, generation_information）に基づき、
    ドキュメント保存用のPathオブジェクトを作成します。
    """
    # 1. ルートディレクトリ
    base_dir = Path(doc_root)
    
    # 2. カテゴリディレクトリ
    category = doc.get("category", "unknown").lower().replace(" ", "_")
    category_dir = base_dir / category
    
    # 3. ファイル名 (nameとモデル名を使用)
    doc_name = doc.get("name", "untitled").replace(" ", "_").replace("/", "_")
    
    # モデル名を取得 (generation_information > model_info、なければ 'N/A')
    model_name = doc.get('generation_information', {}).get('model_info', 'N/A').replace(" ", "_").lower()

    # ファイル名: [name]_[model].json
    file_name = f"{doc_name}_{model_name}.json"
    
    return category_dir / file_name

def _write_documents_to_file_step(doc_root: str, documents: Union[Dict[str, Any], List[Dict[str, Any]]]):
    """Document(Dict)またはDocument List(List[Dict])をファイルに保存する (仮)"""
    if not isinstance(documents, list):
        documents = [documents]
        
    for doc in documents:
        try:
            output_path = _create_document_path(doc, doc_root) # 新しいパス作成関数を使用
            output_path.parent.mkdir(parents = True, exist_ok = True)
            with output_path.open('w', encoding = 'utf-8') as f:
                json.dump(doc, f, ensure_ascii = False, indent = 2)
            print(f"[INFO] Documentを保存: {output_path}", file=sys.stderr)
        except Exception as e:
            print(f"[ERROR] Document保存に失敗: {e}", file=sys.stderr)

def llm_documentation(tasks:Union[ Dict[str, Any],List[Dict[str, Any]]]):
    if not isinstance(tasks,list):
        tasks =[tasks]
        
    for i, task in enumerate(tasks):
        print(f"\n\n========================= タスク {i+1}/{len(tasks)} の処理開始 =========================", file=sys.stderr)
        try:
            #llm_documentation_dict(task)
            create_multisource_document_list(task)
        except Exception as e:
            print(f"タスク {i+1} の実行中に予期せぬエラーが発生しました: {e}", file=sys.stderr)
            continue

def main():
    # 動作確認用テストケース
    tasks = [
        {
            "name": "CASE1: 生成のみ (評価・統合なし)",
            "question": "地球のコアは何で構成されていますか？",
            "model":  ["gemma2:9b","llama3.1:8b", "qwen2:7b","qwen3-coder:30b"], 
            "use_internet_search": True, 
            "internet_search_cash_file_path": "./DocumentAuto/tavily_search_cache.json",
            "encrypted_secrets_path": "./Setting/secrets.enc", 
            "evaluation_model": "", # スキップ
            "integrate_model": "",  # スキップ
            "existing_file_mode": "update",
            "auto_doc_output_folder": "./DocumentAuto/Case1/",

        },
        {
            "name": "CASE2: 既存ファイルを読み込んで評価・ランキング (統合なし)",
            "question": "地球のコアは何で構成されていますか？", # CASE1と同じ質問
            "model":  ["gemma2:9b","llama3.1:8b", "qwen2:7b","qwen3-coder:30b"], 
            "use_internet_search": True, 
            "internet_search_cash_file_path": "./DocumentAuto/tavily_search_cache.json",
            "encrypted_secrets_path": "./Setting/secrets.enc", 
            "evaluation_model": "gemma2:9b", # 評価実行
            "integrate_model": "",           # スキップ
            "existing_file_mode": "skip",    # 既存ファイルを読み出す
            "auto_doc_output_folder": "./DocumentAuto/Case1/",
            "ranking_output_file_path": "./DocumentAuto/Case1/ranking.md"
        },
        {
            "name": "CASE3: 既存ファイルを読み込んで統合 (評価なし)",
            "question": "地球のコアは何で構成されていますか？",
            "model":  ["gemma2:9b","llama3.1:8b", "qwen2:7b","qwen3-coder:30b"], 
            "use_internet_search": True, 
            "internet_search_cash_file_path": "./DocumentAuto/tavily_search_cache.json",
            "encrypted_secrets_path": "./Setting/secrets.enc", 
            "evaluation_model": "",         # スキップ
            "integrate_model": "qwen2:7b",  # 統合実行
            "existing_file_mode": "skip",
            "auto_doc_output_folder": "./DocumentAuto/Case1/",
            "integrate_file_path": "./DocumentAuto/Case1/integrated.md"
        }
    ]
    llm_documentation(tasks)

if __name__ == "__main__":
    main()