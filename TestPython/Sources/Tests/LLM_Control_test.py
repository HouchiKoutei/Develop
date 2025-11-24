import sys
import os
import pytest
from unittest.mock import MagicMock, patch, mock_open
import requests
import time
import subprocess
from requests.exceptions import RequestException, HTTPError, JSONDecodeError
import json

# -------------------------------------------------------------------
# !!! インポートエラー回避のための修正箇所 (デバッグ情報追加) !!!
# -------------------------------------------------------------------
current_dir = os.path.abspath(os.path.dirname(__file__))
project_root_dir = os.path.abspath(os.path.join(current_dir, os.pardir))

if project_root_dir not in sys.path:
    sys.path.insert(0, project_root_dir)
    print(f"--- PATH DEBUG ---")
    print(f"Added directory to sys.path: {project_root_dir}")
    print(f"Please confirm that LLM_Control.py exists exactly in this path.")
    print(f"------------------")

# -------------------------------------------------------------------

from LLM_Control import (
    _wait_for_ollama_ready, _start_ollama_server, _pull_model_if_not_exists, 
    _write_result_to_file, rag_server_register_files, rag_server_query_context, 
    load_files_to_vector_db, retrieve_context_from_db, generate_response,
    RAG_SERVER_URL, OLLAMA_SERVER_URL
)

# ====================================================================
# テスト関数
# ====================================================================

# ... (I/O関数テスト - 変更なし) ...

@patch('requests.get')
@patch('time.sleep', return_value=None)
def test_wait_for_ollama_ready_success(mock_sleep, mock_get):
    """Ollamaがすぐに準備完了になるケースをテストする。"""
    mock_response = MagicMock(status_code=200, text="Ollama is running")
    mock_get.return_value = mock_response
    assert _wait_for_ollama_ready(OLLAMA_SERVER_URL, max_retries=1) == True

@patch('requests.get')
@patch('time.sleep', return_value=None)
def test_wait_for_ollama_ready_retry_success(mock_sleep, mock_get):
    """Ollamaが数回のリトライ後に準備完了になるケースをテストする。"""
    mock_get.side_effect = [
        RequestException,
        MagicMock(status_code=500, text="Server Error"),
        MagicMock(status_code=200, text="Ollama is running")
    ]
    assert _wait_for_ollama_ready(OLLAMA_SERVER_URL, max_retries=5) == True
    assert mock_get.call_count == 3

@patch('requests.get')
@patch('time.sleep', return_value=None)
def test_wait_for_ollama_ready_failure(mock_sleep, mock_get):
    """Ollamaが最大リトライ回数を超えても準備完了にならないケースをテストする。"""
    mock_get.side_effect = RequestException
    with pytest.raises(ConnectionError):
        _wait_for_ollama_ready(OLLAMA_SERVER_URL, max_retries=3)
    assert mock_get.call_count == 3

@patch('subprocess.run')
@patch('subprocess.Popen')
@patch('LLM_Control._wait_for_ollama_ready', return_value=True)
def test_start_ollama_server_already_running(mock_wait, mock_popen, mock_run):
    """Ollamaが既に起動している場合のテスト。"""
    mock_run.return_value = MagicMock(returncode=0)
    _start_ollama_server()
    mock_run.assert_called_once()
    mock_popen.assert_not_called()

@patch('subprocess.run')
@patch('subprocess.Popen')
@patch('LLM_Control._wait_for_ollama_ready', return_value=True)
def test_start_ollama_server_new_start(mock_wait, mock_popen, mock_run):
    """Ollamaを新規に起動し、成功するケースのテスト。"""
    mock_run.side_effect = subprocess.CalledProcessError(1, 'ollama list')
    _start_ollama_server()
    mock_popen.assert_called_once()
    mock_wait.assert_called_once()

@patch('subprocess.run')
@patch('subprocess.Popen')
@patch('LLM_Control._wait_for_ollama_ready')
@patch('sys.exit')
def test_start_ollama_server_command_not_found(mock_exit, mock_wait, mock_popen, mock_run):
    """'ollama' コマンドが見つからない場合のテスト。"""
    mock_run.side_effect = subprocess.CalledProcessError(1, 'ollama list')
    mock_popen.side_effect = FileNotFoundError 
    _start_ollama_server()
    mock_exit.assert_called_once_with(1)

def test_write_result_to_file_success():
    """結果のファイル書き出しが成功するケースのテスト。"""
    m = mock_open()
    with patch('builtins.open', m):
        _write_result_to_file("test_output.txt", "Test Content")
        m.assert_called_once_with("test_output.txt", 'a', encoding='utf-8')
        m().write.assert_called()

def test_write_result_to_file_ioerror():
    """結果のファイル書き出しがIOErrorで失敗するケースのテスト。（追加）"""
    m = mock_open()
    # openの呼び出し自体が例外をスローするように設定
    m.side_effect = IOError("Permission denied") 

    with patch('builtins.open', m):
        with pytest.raises(IOError) as excinfo:
            _write_result_to_file("test_output.txt", "Test Content")
        
        assert "test_output.txt" in str(excinfo.value)

# --------------------------------------------------
# Ollamaクライアント関数テスト (修正適用済み)
# --------------------------------------------------

def test_pull_model_if_not_exists_success():
    """モデルプルが成功し、クライアントの pull が呼び出されることをテスト。"""
    mock_client = MagicMock()
    test_model = "test-model-v2"

    mock_client.pull.return_value = [{'status': 'downloading...'}, {'status': 'success'}] 

    result = _pull_model_if_not_exists(test_model, mock_client)

    assert result == True
    mock_client.pull.assert_called_once_with(model=test_model, stream=True)

def test_pull_model_if_not_exists_pull_failure():
    """モデルプルがクライアント例外で失敗する場合をテスト。"""
    mock_client = MagicMock()
    test_model = "fail-model"

    mock_client.pull.side_effect = Exception("Ollama Pull Error") 

    result = _pull_model_if_not_exists(test_model, mock_client)

    assert result == False 
    mock_client.pull.assert_called_once_with(model=test_model, stream=True)
    
# --------------------------------------------------
# RAGサーバー クライアント関数テスト (エラーケース修正)
# --------------------------------------------------

@patch('builtins.open', new_callable=mock_open)
@patch('requests.post')
@patch('os.path.basename', side_effect=lambda x: x)
def test_rag_server_register_files_success(mock_basename, mock_post, mock_open):
    """ファイル登録が成功するケースのテスト。"""
    mock_file = mock_open(read_data="file content")
    mock_open.return_value = mock_file.return_value

    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = {"status": "ok", "chunks": 10}
    mock_post.return_value = mock_response
    
    with patch('sys.stdout'):
        result = rag_server_register_files(["file.txt"], RAG_SERVER_URL)
    
    assert result == True
    mock_post.assert_called_once()
    
@patch('builtins.open', new_callable=mock_open)
@patch('requests.post')
@patch('os.path.basename', side_effect=lambda x: x)
def test_rag_server_register_files_http_error(mock_basename, mock_post, mock_open):
    """ファイル登録でHTTPエラー (4xx/5xx) が発生するケースをテスト。（修正）"""
    mock_open.return_value = MagicMock()

    mock_response = MagicMock(status_code=404, text="Not Found")
    
    # ★ 修正1: JSONDecodeError を位置引数 (msg, doc, pos) でインスタンス化
    mock_response.json.side_effect = JSONDecodeError("Simulated Decode Failure", "", 0) 
    
    mock_response.raise_for_status.side_effect = HTTPError("404 Client Error: Not Found for url")
    
    mock_post.return_value = mock_response
    
    with patch('sys.stdout'), patch('sys.stderr'):
        result = rag_server_register_files(["file.txt"], RAG_SERVER_URL)
    
    assert result == False
    mock_post.assert_called_once()

# ... (rag_server_register_files_status_error は省略) ...
    

@patch('builtins.open', new_callable=mock_open)
@patch('requests.post')
@patch('os.path.basename', side_effect=lambda x: x)
def test_rag_server_register_files_status_error(mock_basename, mock_post, mock_open):
    """ファイル登録でサーバーが 'error' ステータスを返すケースをテスト。（追加）"""
    mock_open.return_value = MagicMock()

    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = {"status": "error", "message": "Ollama is down"}
    mock_post.return_value = mock_response
    
    with patch('sys.stdout'), patch('sys.stderr'):
        result = rag_server_register_files(["file.txt"], RAG_SERVER_URL)
    
    assert result == False
    mock_post.assert_called_once()

@patch('builtins.open', new_callable=mock_open)
@patch('requests.post')
@patch('os.path.basename', side_effect=lambda x: x)
def test_rag_server_register_files_json_decode_error(mock_basename, mock_post, mock_open):
    """ファイル登録でサーバーが非JSON応答を返すケースをテスト。（修正）"""
    mock_open.return_value = MagicMock()

    mock_response = MagicMock(status_code=200, text="Internal Server Error")
    
    # ★ 修正2: JSONDecodeError を位置引数 (msg, doc, pos) でインスタンス化
    mock_response.json.side_effect = JSONDecodeError(
        "Non-JSON content", 
        "Internal Server Error", 
        0
    )
    mock_post.return_value = mock_response
    
    with patch('sys.stdout'), patch('sys.stderr'):
        result = rag_server_register_files(["file.txt"], RAG_SERVER_URL)
    
    assert result == False
    mock_post.assert_called_once()
    
        
@patch('requests.post')
def test_rag_server_query_context_success(mock_post):
    """コンテキストクエリが成功するケースのテスト。"""
    expected_context = "This is the retrieved context."
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = {"count": 1, "context": expected_context}
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response
    
    with patch('sys.stdout'):
        context = rag_server_query_context("test query", RAG_SERVER_URL)
    
    assert context == expected_context

@patch('requests.post')
def test_rag_server_query_context_network_failure(mock_post):
    """コンテキストクエリがネットワークエラーで失敗するケースをテスト。（追加）"""
    mock_post.side_effect = RequestException("Connection refused")
    
    with patch('sys.stdout'), patch('sys.stderr'):
        context = rag_server_query_context("test query", RAG_SERVER_URL)
    
    assert context == ""
    mock_post.assert_called_once()

# --------------------------------------------------
# コア機能関数テスト
# --------------------------------------------------

@patch('LLM_Control._pull_model_if_not_exists', return_value=True)
@patch('LLM_Control.retrieve_context_from_db', return_value="")
@patch('time.time', side_effect=[100.0, 105.0]) 
def test_generate_response_non_rag_success(mock_time, mock_retrieve, mock_pull):
    """RAG無効時のLLM応答生成成功のテスト。"""
    mock_client = MagicMock()
    mock_client.generate.return_value = {'response': "Answer."}
    
    with patch('sys.stdout'):
        response, latency = generate_response("test-model", "Question", mock_client, db_status=False)
    
    assert response == "Answer."
    assert latency == 5.0
    mock_retrieve.assert_not_called()

@patch('LLM_Control._pull_model_if_not_exists', return_value=True)
@patch('LLM_Control.retrieve_context_from_db', return_value="Context: The answer is 42.")
@patch('time.time', side_effect=[100.0, 108.0])
def test_generate_response_rag_success(mock_time, mock_retrieve, mock_pull):
    """RAG有効時のLLM応答生成成功のテスト。"""
    mock_client = MagicMock()
    mock_client.generate.return_value = {'response': "RAG Answer."}
    
    query = "What is the answer?"
    with patch('sys.stdout'):
        response, latency = generate_response("test-model", query, mock_client, db_status=True)
    
    assert response == "RAG Answer."
    assert latency == 8.0
    mock_retrieve.assert_called_once()
    

if __name__ == "__main__":
    print("\n=== Running tests automatically (pytest mode) ===\n")
    result = pytest.main([os.path.abspath(__file__)])

    if result == 0:
        print("\n🎉 All tests PASSED!\n")
    else:
        print("\n❌ Some tests FAILED. Check log above.\n")