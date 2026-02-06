import os
import yaml
import cv2
import glob
import random
import json
from PIL import Image

# ==========================================
# 制御関数群
# ==========================================

def get_class_names(config):
    """背景フォルダとオブジェクトフォルダからクラス名リストを作成"""
    bg_classes = sorted([os.path.basename(d) for d in glob.glob(os.path.join(config['raw_bg_dir'], "*")) if os.path.isdir(d)])
    obj_classes = sorted([os.path.basename(d) for d in glob.glob(os.path.join(config['raw_obj_dir'], "*")) if os.path.isdir(d)])
    return bg_classes + obj_classes

def generate_data_yaml(config, class_names):
    """data.yamlを自動生成"""
    data_config = {
        'path': os.path.abspath(config['dataset_root']),
        'train': 'images/train',
        'val': 'images/train', # 今回は簡易的に学習データを検証用にも指定
        'names': {i: name for i, name in enumerate(class_names)}
    }
    
    yaml_path = os.path.join(config['dataset_root'], config['yaml_name'])
    os.makedirs(config['dataset_root'], exist_ok=True)
    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(data_config, f, default_flow_style=False, allow_unicode=True)
    
    print(f"[*] {yaml_path} を生成しました。総クラス数: {len(class_names)}")
    return class_names

def create_synthetic_data(config, class_names):
    """画像をランダム配置して教師データを生成"""
    bg_class_dirs = sorted([d for d in glob.glob(os.path.join(config['raw_bg_dir'], "*")) if os.path.isdir(d)])
    obj_class_dirs = sorted([d for d in glob.glob(os.path.join(config['raw_obj_dir'], "*")) if os.path.isdir(d)])
    
    num_bg_classes = len(bg_class_dirs)

    os.makedirs(os.path.join(config['dataset_root'], "images/train"), exist_ok=True)
    os.makedirs(os.path.join(config['dataset_root'], "labels/train"), exist_ok=True)

    extensions = ["**/*.jpg", "**/*.jpeg", "**/*.png", "**/*.JPG", "**/*.PNG"]

    for i in range(config['num_synth_images']):
        # --- 1. 背景の選択 ---
        bg_idx = random.randint(0, num_bg_classes - 1)
        bg_files = []
        for ext in extensions:
            bg_files.extend(glob.glob(os.path.join(bg_class_dirs[bg_idx], ext), recursive=True))
        
        if not bg_files: continue
        
        bg = Image.open(random.choice(bg_files)).convert("RGBA")
        bg_w, bg_h = bg.size
        labels = []
        
        # 背景クラスのラベル (画像全体)
        labels.append(f"{bg_idx} 0.500000 0.500000 1.000000 1.000000")

        # --- 2. オブジェクトのランダム配置 ---
        for _ in range(random.randint(config['min_objs'], config['max_objs'])):
            obj_idx = random.randint(0, len(obj_class_dirs) - 1)
            # クラスIDは背景クラスの数だけオフセットさせる
            target_class_id = num_bg_classes + obj_idx
            
            obj_files = []
            for ext in extensions:
                obj_files.extend(glob.glob(os.path.join(obj_class_dirs[obj_idx], ext), recursive=True))
            
            if not obj_files: continue
                
            obj = Image.open(random.choice(obj_files)).convert("RGBA")
            
            scale = random.uniform(config['scale_min'], config['scale_max'])
            new_size = int(bg_w * scale)
            obj.thumbnail((new_size, new_size))
            obj_w, obj_h = obj.size
            
            cx_pixel = random.randint(obj_w//2, bg_w - obj_w//2)
            cy_pixel = random.randint(obj_h//2, bg_h - obj_h//2)
            bg.paste(obj, (cx_pixel - obj_w//2, cy_pixel - obj_h//2), obj)
            
            labels.append(f"{target_class_id} {cx_pixel/bg_w:.6f} {cy_pixel/bg_h:.6f} {obj_w/bg_w:.6f} {obj_h/bg_h:.6f}")

        # --- 3. 保存 ---
        base_name = f"synth_{i:04d}"
        bg.convert("RGB").save(os.path.join(config['dataset_root'], f"images/train/{base_name}.jpg"))
        with open(os.path.join(config['dataset_root'], f"labels/train/{base_name}.txt"), "w") as f:
            f.write("\n".join(labels))
            
    print(f"[*] {config['num_synth_images']}枚の合成完了。")

import os
import sys
from ultralytics import YOLO

# --- 前述の get_class_names, generate_data_yaml, create_synthetic_data 関数群がここにある前提 ---

def run_training(config):
    """YOLOv8/v11 トレーニング実行"""
    print(f"[*] トレーニングを開始します: epochs={config['epochs']}")
    # モデルの初期化 (既存があればロード、なければ軽量モデルから)
    model = YOLO("yolo11n.pt") 
    
    results = model.train(
        data=os.path.join(config['dataset_root'], config['yaml_name']),
        epochs=config['epochs'],
        imgsz=640,
        batch=config['batch_size'],
        device=config['device']
    )
    print(f"[*] 学習完了: モデルは {config['model_path']} に保存されます。")

def main_process(config):
    # 1. クラス名の事前取得
    all_classes = get_class_names(config)
    
    # 2. モード判定ロジック
    model_exists = os.path.exists(config['model_path'])
    score_is_zero = (config['initial_score'] == 0)

    print(f"--- システム状態確認 ---")
    print(f"モデル存在: {model_exists}, 現在得点: {config['initial_score']}")

    if not model_exists:
        print("\n>>> 【モード1】初期学習モード起動")
        create_synthetic_data(config, all_classes)
        generate_data_yaml(config, all_classes)
        run_training(config)

    elif score_is_zero:
        print("\n>>> 【モード3】リカバリ学習モード起動")
        print("[!] 得点0を検知。残りのステップを学習に割り当てます。")
        # 追加のデータ合成やエポック数の調整など
        create_synthetic_data(config, all_classes) 
        run_training(config)

    else:
        print("\n>>> 【モード2】推論実行モード起動")
        # 推論ロジック (以前の run_inference_test をループ実行)
        # for step in range(config['total_steps']): ...
        print(f"[*] 推論を開始します。残りステップ: {config['total_steps']}")


# ==========================================
# Main
# ==========================================

if __name__ == "__main__":
    app_config = {
        "dataset_root": "dataset",
        "yaml_name": "data.yaml",
        "raw_obj_dir": "raw_materials/objects",
        "raw_bg_dir": "raw_materials/backgrounds",
        "model_path": "runs/detect/train/weights/best.pt",
        "num_synth_images": 50,
        "min_objs": 1,
        "max_objs": 5,
        "scale_min": 0.05,
        "scale_max": 0.2,
        "bg_threshold": 0.9,
            "model_path": "runs/detect/train/weights/best.pt",
        
        # 学習用パラメータ
        "epochs": 50,
        "batch_size": 16,
        "device": "cpu", # GPUなら0, CPUなら'cpu'
        
        # 運用変数
        "initial_score": 100, # ここが0になるとリカバリモード
        "total_steps": 1000,

    }

    main_process(app_config)