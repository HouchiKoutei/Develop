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

def generate_data_yaml(config):
    """フォルダ構成からdata.yamlを自動生成"""
    train_dir = os.path.join(config['dataset_root'], "images/train")
    # フォルダ名からクラス名を取得
    classes = sorted([f for f in os.listdir(train_dir) if os.path.isdir(os.path.join(train_dir, f))])
    
    data_config = {
        'path': os.path.abspath(config['dataset_root']),
        'train': 'images/train',
        'val': 'images/val',
        'names': {i: name for i, name in enumerate(classes)}
    }
    
    yaml_path = os.path.join(config['dataset_root'], config['yaml_name'])
    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(data_config, f, default_flow_style=False, allow_unicode=True)
    
    print(f"[*] {yaml_path} を生成しました。クラス数: {len(classes)}")
    return classes

def create_synthetic_data(config):
    """画像をランダム配置して教師データを生成"""
    bg_images = glob.glob(os.path.join(config['raw_bg_dir'], "*.jpg"))
    obj_dirs = sorted(glob.glob(os.path.join(config['raw_obj_dir'], "*")))
    class_names = [os.path.basename(d) for d in obj_dirs]

    os.makedirs(os.path.join(config['dataset_root'], "images/train"), exist_ok=True)
    os.makedirs(os.path.join(config['dataset_root'], "labels/train"), exist_ok=True)

    for i in range(config['num_synth_images']):
        bg = Image.open(random.choice(bg_images)).convert("RGBA")
        bg_w, bg_h = bg.size
        labels = []

        for _ in range(random.randint(config['min_objs'], config['max_objs'])):
            class_id = random.randint(0, len(class_names) - 1)
            obj_path = random.choice(glob.glob(os.path.join(obj_dirs[class_id], "*.png")))
            obj = Image.open(obj_path).convert("RGBA")
            
            # リサイズ倍率を設定から取得
            scale = random.uniform(config['scale_min'], config['scale_max'])
            new_size = int(bg_w * scale)
            obj.thumbnail((new_size, new_size))
            obj_w, obj_h = obj.size
            
            # ランダム配置
            cx_pixel = random.randint(obj_w//2, bg_w - obj_w//2)
            cy_pixel = random.randint(obj_h//2, bg_h - obj_h//2)
            bg.paste(obj, (cx_pixel - obj_w//2, cy_pixel - obj_h//2), obj)
            
            # YOLO座標変換
            labels.append(f"{class_id} {cx_pixel/bg_w:.6f} {cy_pixel/bg_h:.6f} {obj_w/bg_w:.6f} {obj_h/bg_h:.6f}")

        # 保存
        base_name = f"synth_{i:04d}"
        bg.convert("RGB").save(os.path.join(config['dataset_root'], f"images/train/{base_name}.jpg"))
        with open(os.path.join(config['dataset_root'], f"labels/train/{base_name}.txt"), "w") as f:
            f.write("\n".join(labels))
            
    print(f"[*] {config['num_synth_images']}枚の合成画像を生成完了。")

def run_inference_test(config, test_image_path):
    """学習済みモデルでのテスト推論"""
    from ultralytics import YOLO # 必要な時だけインポート
    model = YOLO(config['model_path'])
    results = model(test_image_path)[0]
    img = cv2.imread(test_image_path)
    h, w, _ = img.shape

    output = {"background": "Unknown", "objects": []}

    for box in results.boxes:
        cls_id = int(box.cls[0])
        label = results.names[cls_id]
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

        # 背景判定ロジック (設定値を使用)
        if (x2 - x1) > (w * config['bg_threshold']) and (y2 - y1) > (h * config['bg_threshold']):
            output["background"] = label
        else:
            output["objects"].append({"name": label, "pos": [cx, cy], "conf": round(float(box.conf[0]), 2)})
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(img, label, (x1, y1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 2)

    print(json.dumps(output, indent=2, ensure_ascii=False))
    cv2.imshow("Test Result", img)
    cv2.waitKey(0)

# ==========================================
# Main プログラム（ここで設定を作成）
# ==========================================

if __name__ == "__main__":
    # 1. 全ての設定をDictionaryとして定義
    app_config = {
        # パス設定
        "dataset_root": "dataset",
        "yaml_name": "data.yaml",
        "raw_obj_dir": "raw_materials/objects",
        "raw_bg_dir": "raw_materials/backgrounds",
        "model_path": "runs/detect/train/weights/best.pt",
        
        # 合成データ作成用パラメータ
        "num_synth_images": 50,  # 生成枚数
        "min_objs": 1,           # 1枚あたりの最小オブジェクト数
        "max_objs": 5,           # 1枚あたりの最大オブジェクト数
        "scale_min": 0.05,       # 物体の最小サイズ(背景比)
        "scale_max": 0.2,        # 物体の最大サイズ(背景比)
        
        # 推論用パラメータ
        "bg_threshold": 0.9      # 画像の何割を占めたら「背景クラス」とみなすか
    }

    # 2. 制御関数に引数として渡して実行
    print("--- 1. 教師データ合成開始 ---")
    create_synthetic_data(app_config)

    print("\n--- 2. YAML設定ファイル生成 ---")
    generate_data_yaml(app_config)

    print("\n--- 3. 推論テスト（学習後を想定） ---")
    # テスト対象の画像があれば実行
    test_target = "test_image.jpg"
    if os.path.exists(test_target):
        run_inference_test(app_config, test_target)
    else:
        print(f"情報: テスト画像 {test_target} がないため推論スキップ")