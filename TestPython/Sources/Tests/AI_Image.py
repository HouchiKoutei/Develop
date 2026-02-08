import os
import yaml
import cv2
import glob
import random
import datetime
import shutil
from PIL import Image
from ultralytics import YOLO

# ==========================================
# 制御関数群
# ==========================================

def get_class_names(config):
    """背景フォルダとオブジェクトフォルダからクラス名リストを動的に作成"""
    bg_root = os.path.abspath(config['raw_bg_dir'])
    obj_root = os.path.abspath(config['raw_obj_dir'])
    bg_classes = sorted([os.path.basename(d) for d in glob.glob(os.path.join(bg_root, "*")) if os.path.isdir(d)])
    obj_classes = sorted([os.path.basename(d) for d in glob.glob(os.path.join(obj_root, "*")) if os.path.isdir(d)])
    return bg_classes, obj_classes

def generate_data_yaml(config, all_classes):
    """data.yamlを自動生成"""
    data_config = {
        'path': os.path.abspath(config['dataset_root']),
        'train': 'images/train',
        'val': 'images/train',
        'names': {i: name for i, name in enumerate(all_classes)}
    }
    os.makedirs(config['dataset_root'], exist_ok=True)
    yaml_path = os.path.join(config['dataset_root'], config['yaml_name'])
    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(data_config, f, default_flow_style=False, allow_unicode=True)

def create_synthetic_data(config, bg_classes, obj_classes):
    """教師データを生成"""
    os.makedirs(os.path.join(config['dataset_root'], "images/train"), exist_ok=True)
    os.makedirs(os.path.join(config['dataset_root'], "labels/train"), exist_ok=True)
    exts = ["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.PNG"]
    num_bg = len(bg_classes)

    for i in range(config['num_synth_images']):
        bg_idx = random.randint(0, num_bg - 1)
        bg_dir = os.path.join(config['raw_bg_dir'], bg_classes[bg_idx])
        bg_files = []
        for e in exts: bg_files.extend(glob.glob(os.path.join(bg_dir, e)))
        if not bg_files: continue

        bg = Image.open(random.choice(bg_files)).convert("RGBA")
        bg_w, bg_h = bg.size
        labels = [f"{bg_idx} 0.5 0.5 1.0 1.0"]

        for _ in range(random.randint(config['min_objs'], config['max_objs'])):
            obj_idx = random.randint(0, len(obj_classes) - 1)
            target_id = num_bg + obj_idx
            obj_dir = os.path.join(config['raw_obj_dir'], obj_classes[obj_idx])
            obj_files = []
            for e in exts: obj_files.extend(glob.glob(os.path.join(obj_dir, e)))
            if not obj_files: continue

            obj = Image.open(random.choice(obj_files)).convert("RGBA")
            scale = random.uniform(config['scale_min'], config['scale_max'])
            new_sz = int(bg_w * scale)
            obj.thumbnail((new_sz, new_sz))
            ow, oh = obj.size
            cx, cy = random.randint(ow//2, bg_w-ow//2), random.randint(oh//2, bg_h-oh//2)
            bg.paste(obj, (cx - ow//2, cy - oh//2), obj)
            labels.append(f"{target_id} {cx/bg_w:.6f} {cy/bg_h:.6f} {ow/bg_w:.6f} {oh/bg_h:.6f}")

        base = f"synth_{datetime.datetime.now().strftime('%H%M%S')}_{i:03d}"
        bg.convert("RGB").save(os.path.join(config['dataset_root'], f"images/train/{base}.jpg"))
        with open(os.path.join(config['dataset_root'], f"labels/train/{base}.txt"), "w") as f:
            f.write("\n".join(labels))

def run_training(config):
    """学習の実行"""
    print(f"\n>>> 【学習開始】エポック数: {config['epochs']}")
    model_src = config['model_path'] if os.path.exists(config['model_path']) else "yolo11n.pt"
    model = YOLO(model_src)
    model.train(
        data=os.path.join(config['dataset_root'], config['yaml_name']),
        epochs=config['epochs'],
        batch=config['batch_size'],
        device=config['device'],
        exist_ok=True
    )

# ==========================================
# 修正済み: 自動分別
# ==========================================

def run_auto_sorting(config, bg_classes, obj_classes):
    print("\n>>> 【機能1】自動分別を開始します")
    if not os.path.exists(config['model_path']):
        print("[!] モデルがないため分別をスキップします。")
        return

    model = YOLO(config['model_path'])
    num_bg = len(bg_classes)
    target_files = []
    for ext in ["*.jpg", "*.png", "*.jpeg", "*.JPG", "*.PNG"]:
        target_files.extend(glob.glob(os.path.join(config['sort_target_dir'], ext)))

    for img_path in target_files:
        # 手動移動対策: 処理直前にファイル存在チェック
        if not os.path.exists(img_path):
            continue

        try:
            results = model(img_path, conf=config['conf_threshold'], verbose=False)[0]
            
            detected_bg = None
            detected_objs = set()

            for box in results.boxes:
                cls_id = int(box.cls[0])
                name = results.names[cls_id]
                if cls_id < num_bg:
                    if detected_bg is None: detected_bg = name
                else:
                    detected_objs.add(name)
            
            # 判定: 何も検出されなかったなら移動しない
            if detected_bg is None and not detected_objs:
                continue
            
            # フォルダ名構築
            bg_part = detected_bg if detected_bg else "_"
            obj_str = "_".join(sorted(list(detected_objs)))
            folder_name = f"{bg_part}({obj_str})" if obj_str else f"{bg_part}"
            
            dest_dir = os.path.join(config['sort_target_dir'], folder_name)
            os.makedirs(dest_dir, exist_ok=True)
            
            # 移動先との競合を避けるため
            shutil.move(img_path, os.path.join(dest_dir, os.path.basename(img_path)))
        except Exception as e:
            print(f"[!] エラーによりスキップ ({os.path.basename(img_path)}): {e}")
            continue
            
    print(f"[*] 分別完了")

def run_click_test(config):
    print("\n>>> 【機能2】自動クリックテストを開始します")
    if not os.path.exists(config['model_path']): return
    model = YOLO(config['model_path'])
    success = 0
    imgs = glob.glob(os.path.join(config['dataset_root'], "images/train/*.jpg"))
    if not imgs: return
    samples = random.sample(imgs, min(len(imgs), config['test_count']))
    for p in samples:
        lab = p.replace("images", "labels").replace(".jpg", ".txt")
        if not os.path.exists(lab): continue
        with open(lab, 'r') as f:
            lines = f.readlines()
            if len(lines) < 2: continue
            _, tx, ty, _, _ = map(float, lines[1].split())
        res = model(p, verbose=False)[0]
        for box in res.boxes:
            bx, by, _, _ = box.xywh[0]
            if abs(bx/res.orig_shape[1]-tx)<0.05 and abs(by/res.orig_shape[0]-ty)<0.05:
                success += 1
                break
    rate = (success/len(samples))*100
    with open(config['log_path'], "a") as f:
        f.write(f"[{datetime.datetime.now()}] Rate:{rate:.2f}%\n")
    print(f"[*] テスト成功率: {rate:.2f}%")

# ==========================================
# メイン
# ==========================================

def main_process(config):
    bg_classes, obj_classes = get_class_names(config)
    if not bg_classes: 
        print("[!] 背景クラスが見つかりません。")
        return
    all_classes = bg_classes + obj_classes
    generate_data_yaml(config, all_classes)

    model_exists = os.path.exists(config['model_path'])

    if not model_exists or config['initial_score'] == 0:
        print("\n>>> 【学習モード起動】")
        create_synthetic_data(config, bg_classes, obj_classes)
        run_training(config)
    else:
        print("\n--- 運用メニュー ---")
        choice = input("自動分別を実行しますか？ (y/n): ").lower()
        
        if choice == 'y':
            run_auto_sorting(config, bg_classes, obj_classes)
        else:
            print("[*] 分別をスキップしました。")

        run_click_test(config)
        
        print("\n>>> 【運用後学習】精度向上のためデータを生成し学習します")
        create_synthetic_data(config, bg_classes, obj_classes)
        run_training(config)

if __name__ == "__main__":
    app_config = {
        "dataset_root": "dataset",
        "yaml_name": "data.yaml",
        "raw_bg_dir": r"D:\Files\all",
        "raw_obj_dir": r"Images\objects",
        "sort_target_dir": r"D:\Files\all",
        "model_path": r"runs\detect\train\weights\best.pt",
        "log_path": "test_log.txt",
        "num_synth_images": 50,
        "min_objs": 1, "max_objs": 5,
        "scale_min": 0.05, "scale_max": 0.2,
        "epochs": 10,
        "batch_size": 16,
        "device": "cpu",
        "initial_score": 100,
        "test_count": 100,
        "conf_threshold": 0.5
    }
    main_process(app_config)