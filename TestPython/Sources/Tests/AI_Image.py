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
    """指定順に座標を計算"""
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
    num_bg = len(bg_classes) # 背景クラスの数を確認
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
                # IDが背景クラス数未満なら背景、それ以上ならオブジェクト
                if cls_id < num_bg:
                    if det_bg is None: det_bg = name
                else:
                    det_objs.add(name)
            
            # 背景と物の両方を使ってフォルダ名を生成
            f_name = build_folder_name(det_bg, det_objs)
            if f_name:
                dest_dir = os.path.join(config['sort_target_dir'], f_name)
                os.makedirs(dest_dir, exist_ok=True)
                shutil.move(img_path, os.path.join(dest_dir, os.path.basename(img_path)))
        except Exception: continue
    print(f"[*] 分別完了")
    
def run_click_test(config):
    """精度テストを実行し、精度スコア(0-100)を返す"""
    print("\n>>> 【内部テスト】推論精度を確認中...")
    if not os.path.exists(config['model_path']): return 0
    model = YOLO(config['model_path'])
    success = 0
    imgs = glob.glob(os.path.join(config['dataset_root'], "images/train/*.jpg"))
    if not imgs: return 0
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
    print(f"[*] 現在の精度スコア: {rate:.2f}%")
    return rate

def run_live_visual_test(config, system):
    """実機ウィンドウ表示テスト"""
    print("\n>>> 【実機テスト】画像を画面に表示して認識・クリックします")
    imgs = glob.glob(os.path.join(config['dataset_root'], "images/train/*.jpg"))
    if not imgs: return
    test_img = cv2.imread(random.choice(imgs))
    win_name = "AI_VISUAL_TEST"
    cv2.namedWindow(win_name, cv2.WINDOW_AUTOSIZE)
    cv2.moveWindow(win_name, 100, 100)
    cv2.imshow(win_name, test_img)
    cv2.waitKey(1000)
    print("[*] 画像表示中... 3秒後にクリックテストを実行します。")
    import time
    time.sleep(3)
    system.capture_and_click([]) # 検出したものを全てクリックする
    cv2.destroyAllWindows()

# ==========================================
# 3. 統合管理クラス
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
        if not self.model: return
        screen = np.array(ImageGrab.grab())
        screen_bgr = cv2.cvtColor(screen, cv2.COLOR_RGB2BGR)
        results = self.model(screen_bgr, conf=self.config['conf_threshold'], verbose=False)[0]
        
        if not target_list: # テスト用：検出された全オブジェクト
            points = [(int(b.xywh[0][0]), int(b.xywh[0][1])) for b in results.boxes]
        else:
            points = resolve_click_targets(results, target_list)
            
        for x, y in points:
            ctypes.windll.user32.SetCursorPos(x, y)
            ctypes.windll.user32.mouse_event(2, 0, 0, 0, 0)
            ctypes.windll.user32.mouse_event(4, 0, 0, 0, 0)
            print(f"[*] Clicked: ({x}, {y})")

    def run_file_sorting(self):
        run_auto_sorting(self.config, self.bg_classes, self.obj_classes)

    def run_training_cycle(self):
        print("\n>>> 学習サイクル開始")
        create_synthetic_data(self.config, self.bg_classes, self.obj_classes)
        run_training(self.config)
        self._model = None # 次回利用時にリロード

# ==========================================
# 4. メイン処理
# ==========================================

def main_process(config):
    system = AIAutomation(config)
    
    # --- モード選択フェーズ ---
    print("=== AI Image Recognition System ===")
    ans_sort = input("1. フォルダ分別を実行しますか？ (y/n): ").lower()
    train_mode = input("2. 学習モードを選択 (1:単発 / 2:目標精度に達するまでループ / 0:スキップ): ")
    
    target_accuracy = 95.0 # デフォルト
    if train_mode == '2':
        val = input(f"   - 目標とする精度(%)を入力してください [デフォルト: {target_accuracy}]: ")
        if val.strip() != "":
            try:
                target_accuracy = float(val)
            except ValueError:
                print(f"[!] 数値として認識できませんでした。デフォルトの {target_accuracy}% を使用します。")

    # 実行1: 分別
    if ans_sort == 'y':
        system.run_file_sorting()

    # 前準備 (クラス名の確定とYAML更新)
    bg_classes, obj_classes = system.bg_classes, system.obj_classes
    if not bg_classes: return print("[!] 背景クラスが見つかりません。")
    all_classes = bg_classes + obj_classes
    generate_data_yaml(config, all_classes)

    # 実行2: 学習ループ
    if train_mode in ['1', '2']:
        while True:
            create_synthetic_data(config, system.bg_classes, system.obj_classes)
            run_training(config)
            system._model = None # 最新モデルのリロード
            
            if train_mode == '1': 
                run_click_test(config) # 単発の場合は確認のみして終了
                break
            
            current_acc = run_click_test(config)
            if current_acc >= target_accuracy:
                print(f"[SUCCESS] 目標精度 {target_accuracy}% を達成しました。")
                break
            else:
                print(f"[RETRY] 現在 {current_acc:.2f}%。目標 {target_accuracy}% まで再学習します。")

    # 実行3: 実機テストと運用
    if os.path.exists(config['model_path']):
        # 実機テスト
        run_live_visual_test(config, system)
        
        # 本番シーケンス
        target_sequence = [("Icon_放置少女V", 1), "酒", "1010_return"]
        print("\n>>> 指定された操作シーケンスを開始します...")
        import time
        time.sleep(1)
        system.capture_and_click(target_sequence)

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
        "conf_threshold": 0.5,
        "test_count": 50
    }
    main_process(app_config)