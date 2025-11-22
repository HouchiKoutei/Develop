import re
import random
from typing import Dict, Optional, Tuple, List, Union, Any
import random
import copy

def split_text_including_delimiters(text: str, delimiters: List[str]) -> List[str]:
    """
    文字列を区切り文字を含めて分割する純粋関数

    Args:
        text (str): 分割対象の文字列
        delimiters (List[str]): 区切り文字のリスト

    Returns:
        List[str]: 分割された文字列のリスト
    """
    parts = []
    start = 0
    for i, char in enumerate(text):
        if char in delimiters:
            parts.append(text[start:i])
            parts.append(char)
            start = i + 1
    parts.append(text[start:])
    return parts

def split_including_delimiters(source: Union[str, List[str]], delimiters: List[str]) -> List[Any]:
    """
    文字列または文字列リストを複数の区切り文字を含めて分割する純粋関数

    Args:
        text (Union[str, List[str]]): 分割対象の文字列または文字列リスト
        delimiters (List[str]): 区切り文字のリスト

    Returns:
        List[Any]: 分割された要素のリスト (文字列またはリスト)
    """

    if isinstance(source, str):
        return split_text_including_delimiters(source, delimiters)
    elif isinstance(source, list):
        item = []
        for text in source:
            item.extend(split_text_including_delimiters(text, delimiters))
        return item
    else:
        raise TypeError("Input must be a string or a list of strings.")

def multi_split(text, delimiters):
    """
    複数の区切り文字を1つに統一し、重複する区切り文字を単一にして文字列を分割する関数

    Args:
        text (str): 分割対象の文字列
        delimiters (list): 区切り文字のリスト
        unified_delimiter (str, optional): 統一する区切り文字 (デフォルト: " ")

    Returns:
        list: 分割された文字列のリスト
    """
    if delimiters == []:
        if isinstance(text,list):
            return text
        else:
            return [text]
    unified_delimiter=""
    for delimiter in delimiters:
        unified_delimiter = delimiter
        if unified_delimiter != "":
            break
    # 正規表現パターンを作成
    pattern = "|".join(map(re.escape, delimiters))

    # 区切り文字を統一し、重複する区切り文字を単一にする
    normalized_text = re.sub(r"(" + pattern + ")+", unified_delimiter, text)

    # 文字列を分割
    result = normalized_text.split(unified_delimiter)

    # 空文字列を取り除く
    result = list(filter(None, result))

    return result




def pop_sequential(lst: List[Any]) -> Any:
    """リストから順番に値を取り出す (正順)"""
    if not lst:
        return None
    return lst.pop(0)

def pop_reverse(lst: List[Any]) -> Any:
    """リストから逆順に値を取り出す"""
    if not lst:
        return None
    return lst.pop()

def pop_random(lst: List[Any]) -> Any:
    """リストからランダムに値を取り出す"""
    if not lst:
        return None
    index = random.randint(0, len(lst) - 1)
    return lst.pop(index)

def pop_from_list(source_list, order="sequential",):
    """リスト処理のメイン関数"""
    if order == "reverse":
        return  pop_reverse(source_list)
    elif order == "random":
        return  pop_random(source_list)
    else:
        return pop_sequential(source_list)
    
def deepcopy_selected_keys(source_dict: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    """
    指定されたキーのみを deepcopy して新しい辞書を作成する純粋関数

    Args:
        source_dict (Dict[str, Any]): コピー元の辞書
        keys (List[str]): コピーするキーのリスト

    Returns:
        Dict[str, Any]: 指定されたキーのみを deepcopy した辞書
    """
    return {key: copy.deepcopy(source_dict[key]) for key in keys if key in source_dict}

def get_next_value(pop_target_lists: Dict[str, List[Any]], source: str, order: str, list_end: str, original_lists: Dict[str, List[Any]]) -> Any:
    if source not in pop_target_lists:
        pop_target_lists[source] = copy.deepcopy(original_lists.get(source, []))
    
    value = pop_from_list(pop_target_lists[source], order)
    
    if value is None and list_end == "continue":
        pop_target_lists[source] = copy.deepcopy(original_lists.get(source, []))
        return get_next_value(pop_target_lists, source, order, list_end, original_lists)
    return value

def get_next_all(pop_settings: Dict[str, Any], pop_target_lists: Dict[str, List[Any]], original_lists: Dict[str, List[Any]]) -> Union[Dict[str, Any], None]:
    result = {}
    for key, config in pop_settings.items():
        if isinstance(config, dict):
            value = get_next_value(pop_target_lists, config.get("source", ""), config.get("order", "sequential"), config.get("list_end", "stop"), original_lists)
        else:
            value = get_next_value(pop_target_lists, config, "sequential", "stop", original_lists)
        
        if value is None:
            return None
        result[key] = value
    return result

def get_pop_keys(pop_settings: Dict[str, Any]) -> List[str]:
    """
    pop_settings から "source" の値を抽出し、キーリストを返す関数

    Args:
        pop_settings (Dict[str, Any]): ポップ設定の辞書

    Returns:
        List[str]: 抽出したキーのリスト
    """
    keys = []
    for config in pop_settings.values():
        if isinstance(config, dict):
            source = config.get("source")
            if source:
                keys.append(source)
        else:
            keys.append(config)
    return keys

def replace_list_values(list_data: Union[Any, List[Any]], replace_dictionary: Dict[str, str]) -> List[Any]:
    """
    元のリストを変更せず、置換設定に従って新しいリストを作成する。

    Args:
        list_data (Union[Any, List[Any]]): 置換前のリストまたは単一要素
        replace_dictionary (Dict[str, str]): 置換設定（元の値: 置換後の値）

    Returns:
        List[Any]: 置換後の新しいリスト
    """
    if not isinstance(list_data, list):
        list_data = [list_data]

    result = []
    for item in list_data:
        if isinstance(item, str):
            result.append(replace_dictionary.get(item, item))
        else:
            result.append(item)
    return result



def format_merge_multiple_list(
    format_string: str,
    placeholder_format: Union[str, List[Union[str, None]]] = "list{index}_",
    **str_lists: List[Any]
) -> List[str]:
    """
    複数のリストを指定フォーマットで結合し、足りない部分を補完する汎用関数。
    """
    result = []
    max_length = 0
    for key, value in str_lists.items():
        if not isinstance(value, list):
            str_lists[key] = [value]
        max_length = max(max_length, len(str_lists[key]))

    if isinstance(placeholder_format, str):
        placeholder_format = [placeholder_format] * len(str_lists)

    list_keys = list(str_lists.keys())

    for i in range(max_length):
        formatted_lists = {}

        for idx, key in enumerate(list_keys):
            values = str_lists[key]
            if i < len(values):
                formatted_lists[key] = str(values[i])
            else:
                if idx < len(placeholder_format) and placeholder_format[idx] is not None:
                    try:
                        formatted_lists[key] = placeholder_format[idx].format(index=i+1)
                    except Exception as e:
                        raise ValueError(f"プレースホルダーのフォーマットに失敗しました: {placeholder_format[idx]} (index={i+1}) - {e}") from e

        try:
            formatted_str = format_string.format(**{k: v for k, v in formatted_lists.items() if v is not None})
        except KeyError as e:
            missing_key = e.args[0]
            raise ValueError(f"フォーマット文字列で指定されたキー '{missing_key}' が提供されていません。formatted_lists={formatted_lists}") from e
        except Exception as e:
            raise ValueError(f"フォーマット処理中にエラーが発生しました: {e}") from e

        result.append(formatted_str)

    return result
def include_filter(target_list, filter_list):
    return [item for item in target_list if item in filter_list]

def exclude_filter(target_list, filter_list):
    return [item for item in target_list if item not in filter_list]

def main():
    # 設定
    settings = {
        "file_path": "file_list",
        "value": {"source": "value_list", "order": "random", "list_end": "continue"},
        "date": {"source": "date_list", "order": "reverse", "list_end": "stop"}
    }

    # テストデータ
    data_list_dictionary = {
        "file_list": ["file1.txt", "file2.txt", "file3.txt"],
        "value_list": [10, 20, 30],
        "date_list": ["2024-02-01", "2024-02-02", "2024-02-03"],
    }

    # 必要なキーを抽出し、初期化
    keys = [config["source"] if isinstance(config, dict) else config for config in settings.values()]
    pop_target_lists = deepcopy_selected_keys( data_list_dictionary,keys)

    # テスト
    for _ in range(5):
        result = get_next_all(settings, pop_target_lists, data_list_dictionary)
        print(result)
        if result is None:
            break

    pop_target_lists = deepcopy_selected_keys( data_list_dictionary,keys)

    print("=== file_path (sequential / stop) ===")
    for _ in range(5):
        print(get_next_value(pop_target_lists, "file_list", "sequential", "stop", data_list_dictionary))

    print("\n=== value (random / continue) ===")
    for _ in range(6):
        print(get_next_value(pop_target_lists, "value_list", "random", "continue", data_list_dictionary))

    print("\n=== date (reverse / stop) ===")
    for _ in range(5):
        print(get_next_value(pop_target_lists, "date_list", "reverse", "stop", data_list_dictionary))
    # 使用例
    list_data = ["A", "B", "C"]
    replace_dictionary = {"A": "D", "B": "E"}

    new_list = replace_list_values(list_data, replace_dictionary)
    print(new_list)  # ['D', 'E', 'C']
    print(list_data)  # ['A', 'B', 'C']  (元のリストは変更されていない)
        
if __name__ == '__main__':
    main()
