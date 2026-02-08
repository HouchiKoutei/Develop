import os
import yaml
import cv2
import glob
import random
import datetime
import shutil
import ctypes
import numpy as np
from PIL import Image, ImageGrab
from ultralytics import YOLO

# ==========================================
# 1. 純粋関数群 (Pure Logic)
# ==========================================

def get_class_names(config):
    """フォルダ構成から動的にクラス名を取得"""
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

def build_folder_name(detected_bg, detected_objs):
    """推論結果から移動先フォルダ名を生成"""
    if detected_bg is None and not detected_objs:
        return None
    bg_part = detected_bg if detected_bg else "_"
    obj_str = "_".join(sorted(list(detected_objs)))
    return f"{bg_part}({obj_str})" if obj_str else f"{bg_part}"

def resolve_click_targets(results, target_list):
    """指定されたターゲットリスト順に座標を計算。target_list: ["酒", ("ボタン", 2)]"""
    click_points = []
    for item in target_list:
        label = item[0] if isinstance(item, (list, tuple)) else item
        index = item[1] if isinstance(item, (list, tuple)) else 1
        
        coords = []
        for box in results.boxes:
            cls_id = int(box.cls[0])
            if results.names[cls_id] == label:
                bx, by, _, _ = box.xywh[0].tolist()
                coords.append((int(bx), int(by)))
        
        if 1 <= index <= len(coords):
            click_points.append(coords[index - 1])
    return click_points

# ==========================================
# 2. 副作用関数群 (I/O & Execution)
# ==========================================

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
        epochs=config['epochs'], batch=config['batch_size'], device=config['device'], exist_ok=True
    )

def run_auto_sorting(config, bg_classes, obj_classes):
    """自動分別実行"""
    print("\n>>> 【機能1】自動分別を開始します")
    if not os.path.exists(config['model_path']):
        return print("[!] モデルがないため分別をスキップします。")

    model = YOLO(config['model_path'])
    num_bg = len(bg_classes)
    target_files = []
    for ext in ["*.jpg", "*.png", "*.jpeg", "*.JPG", "*.PNG"]:
        target_files.extend(glob.glob(os.path.join(config['sort_target_dir'], ext)))

    for img_path in target_files:
        if not os.path.exists(img_path): continue
        try:
            results = model(img_path, conf=config['conf_threshold'], verbose=False)[0]
            det_bg, det_objs = None, set()
            for box in results.boxes:
                cls_id = int(box.cls[0])
                name = results.names[cls_id]
                if cls_id < num_bg:
                    if det_bg is None: det_bg = name
                else: det_objs.add(name)
            
            f_name = build_folder_name(det_bg, det_objs)
            if f_name:
                dest_dir = os.path.join(config['sort_target_dir'], f_name)
                os.makedirs(dest_dir, exist_ok=True)
                shutil.move(img_path, os.path.join(dest_dir, os.path.basename(img_path)))
        except Exception as e: continue
    print(f"[*] 分別完了")

def run_click_test(config):
    """合成画像を使用したクリックテスト"""
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
# 3. 統合管理クラス (AIAutomation)
# ==========================================

class AIAutomation:
    def __init__(self, config):
        self.config = config
        self.bg_classes, self.obj_classes = get_class_names(config)
        self._model = None

    @property
    def model(self):
        if self._model is None and os.path.exists(self.config['model_path']):
            self._model = YOLO(self.config['model_path'])
        return self._model

    def capture_and_click(self, target_list):
        """デスクトップキャプチャと指定順クリック"""
        if not self.model: return print("[!] モデルがありません")
        screen = np.array(ImageGrab.grab())
        screen_bgr = cv2.cvtColor(screen, cv2.COLOR_RGB2BGR)
        results = self.model(screen_bgr, conf=self.config['conf_threshold'], verbose=False)[0]
        points = resolve_click_targets(results, target_list)
        for x, y in points:
            ctypes.windll.user32.SetCursorPos(x, y)
            ctypes.windll.user32.mouse_event(2, 0, 0, 0, 0) # Down
            ctypes.windll.user32.mouse_event(4, 0, 0, 0, 0) # Up
            print(f"[*] Clicked: ({x}, {y})")

    def run_file_sorting(self):
        run_auto_sorting(self.config, self.bg_classes, self.obj_classes)

    def run_training_cycle(self):
        print("\n>>> 学習サイクル開始")
        create_synthetic_data(self.config, self.bg_classes, self.obj_classes)
        run_training(self.config)
        self._model = None # 次回利用時にリロード

# ==========================================
# 4. メイン処理 (Main Process)
# ==========================================

def main_process(config):
    # クラス初期化
    system = AIAutomation(config)
    
    # 1. 冒頭の分別確認
    if input("今すぐ分別を実行しますか？ (y/n): ").lower() == 'y':
        system.run_file_sorting()

    # クラス名の確定とYAML更新
    bg_classes, obj_classes = system.bg_classes, system.obj_classes
    if not bg_classes: return print("[!] 背景クラスが見つかりません。")
    all_classes = bg_classes + obj_classes
    generate_data_yaml(config, all_classes)

    model_exists = os.path.exists(config['model_path'])

    if not model_exists or config['initial_score'] == 0:
        print("\n>>> 【学習モード起動】")
        system.run_training_cycle()
    else:
        run_click_test(config)

        # クリック操作の実行
        target_sequence = [("Icon_放置少女V", 1), "酒", "1010_return"]
        print("3秒後に画面認識クリックを開始します...")
        import time
        time.sleep(3)
        system.capture_and_click(target_sequence)

        # 最後に運用後学習
        print("\n>>> 【運用後学習】精度向上のためデータを生成し学習します")
        system.run_training_cycle()

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