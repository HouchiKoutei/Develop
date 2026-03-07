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
import pyautogui
from pathlib import Path

# ==========================================
# 1. 純粋関数群 (Pure Logic)
# ==========================================

def load_or_update_master_classes(config):
    """マスタリストを読み込み、新規フォルダがあれば末尾に追記する"""
    master_path = config['master_list_path']
    
    # 現在のフォルダ構成をスキャン
    bg_root = os.path.abspath(config['raw_bg_dir'])
    obj_root = os.path.abspath(config['raw_obj_dir'])
    found_bg = sorted([os.path.basename(d) for d in glob.glob(os.path.join(bg_root, "*")) if os.path.isdir(d)])
    found_obj = sorted([os.path.basename(d) for d in glob.glob(os.path.join(obj_root, "*")) if os.path.isdir(d)])
    
    # マスタリストの読み込み
    master_bg = []
    master_obj = []
    
    if os.path.exists(master_path):
        with open(master_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
            # 背景と物を分けるためのセパレータ（[OBJECTS]など）を設ける運用も可能ですが、
            # 今回はシンプルに、既存リストにあるものはそのまま、ないものは末尾に追加します。
            # ※本来は背景と物を厳密に分けたいところですが、運用上「一度決まったIDを変えない」ことを優先します。
            master_all = lines
    else:
        master_all = []

    # 未登録の背景を追加
    for b in found_bg:
        if b not in master_all:
            master_all.append(b)
            print(f"[*] 新規背景クラスを登録: {b}")
    
    # 未登録のオブジェクトを追加
    for o in found_obj:
        if o not in master_all:
            master_all.append(o)
            print(f"[*] 新規オブジェクトクラスを登録: {o}")

    # 保存
    with open(master_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(master_all))
    
    # YOLO用に背景クラスのリストと、オブジェクトクラスのリストを現在のマスタから再整理
    # (背景クラスが先頭に来るように管理するのが自動分別のために必要です)
    bg_classes = [c for c in master_all if c in found_bg]
    obj_classes = [c for c in master_all if c in found_obj]
    
    return master_all, bg_classes, obj_classes

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
# 2. 副作用関数群 (ID指定をマスタ依存に修正)
# ==========================================
def create_synthetic_data(config, all_classes, bg_classes, obj_classes):
    """教師データを生成（マスタリストのIDを使用）"""
    
    # ガード処理を追加
    if not bg_classes:
        print(f"[!] 背景クラスが見つかりません。ディレクトリを確認してください: {config['raw_bg_dir']}")
        return
    if not obj_classes:
        print(f"[!] オブジェクトクラスが見つかりません。ディレクトリを確認してください: {config['raw_obj_dir']}")
        return

    """教師データを生成（マスタリストのIDを使用）"""
    os.makedirs(os.path.join(config['dataset_root'], "images/train"), exist_ok=True)
    os.makedirs(os.path.join(config['dataset_root'], "labels/train"), exist_ok=True)
    exts = ["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.PNG"]

    for i in range(config['num_synth_images']):
        # 背景の選択とID取得
        bg_name = random.choice(bg_classes)
        bg_idx = all_classes.index(bg_name) # マスタ内のID
        
        bg_dir = os.path.join(config['raw_bg_dir'], bg_name)
        bg_files = []
        for e in exts: bg_files.extend(glob.glob(os.path.join(bg_dir, e)))
        if not bg_files: continue

        bg = Image.open(random.choice(bg_files)).convert("RGBA")
        bg_w, bg_h = bg.size
        labels = [f"{bg_idx} 0.5 0.5 1.0 1.0"]

        for _ in range(random.randint(config['min_objs'], config['max_objs'])):
            obj_name = random.choice(obj_classes)
            target_id = all_classes.index(obj_name) # マスタ内のID
            
            obj_dir = os.path.join(config['raw_obj_dir'], obj_name)
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

def run_auto_sorting(config, all_classes, bg_classes):
    """自動分別実行（マスタIDで背景か物かを判定）"""
    print("\n>>> 【機能1】自動分別を開始します")
    if not os.path.exists(config['model_path']):
        return print("[!] モデルがないためスキップ。")
    
    model = YOLO(config['model_path'])
    
    target_files = []
    for ext in ["*.jpg", "*.png", "*.jpeg", "*.JPG", "*.PNG"]:
        target_files.extend(glob.glob(os.path.join(config['sort_target_dir'], ext)))

    if not target_files:
        print("[*] 分別対象のファイルが見つかりませんでした。")
        return

    moved_count = 0
    for img_path in target_files:
        if not os.path.exists(img_path): continue
        try:
            results = model(img_path, conf=config['conf_threshold'], verbose=False)[0]
            det_bg, det_objs = None, set()
            for box in results.boxes:
                name = results.names[int(box.cls[0])]
                if name in bg_classes:
                    if det_bg is None: det_bg = name
                else:
                    det_objs.add(name)
            
            f_name = build_folder_name(det_bg, det_objs)
            if f_name:
                dest_dir = os.path.join(config['sort_target_dir'], f_name)
                os.makedirs(dest_dir, exist_ok=True)
                
                # 移動処理とログ表示
                file_name = os.path.basename(img_path)
                shutil.move(img_path, os.path.join(dest_dir, file_name))
                print(f" [MOVE] {file_name} -> {f_name}/")
                moved_count += 1
                
        except Exception as e:
            print(f" [!] 移動失敗 ({os.path.basename(img_path)}): {e}")
            continue
            
    print(f"[*] 分別完了 (計 {moved_count} 個のファイルを整理しました)")
    
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

def find_position(target, system, confidence=0.8):
    """
    pathlibを使用して、/ を含むパスをOSに依存せず正しく扱う
    """
    target = target.strip()
    
    # 1. パスとしての判定
    # 文字列をPathオブジェクトに変換
    target_path = Path(target)
    
    # ファイル名として画像拡張子を持っているか、または実在するパスかをチェック
    is_image_file = target_path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.bmp']
    
    if is_image_file or target_path.exists():
        # .resolve() を使うことで、スラッシュの向きをOSに合わせて解決し、絶対パスにする
        abs_path = str(target_path.resolve())
        
        if target_path.exists():
            print(f"[*] 画像ファイルとして探索中: {abs_path}")
            try:
                pos = pyautogui.locateCenterOnScreen(abs_path, confidence=confidence)
                if pos:
                    return (int(pos.x), int(pos.y))
            except Exception as e:
                print(f"[!] PyAutoGUIエラー: {e}")
        else:
            # 拡張子的にパスなのに、ファイルが物理的に見つからない場合
            print(f"[!] 指定された画像パスが見つかりません: {abs_path}")
        return None

    # 2. YOLOのクラス名として探索
    else:
        print(f"[*] YOLOクラスとして探索中: {target}")
        model = system.model
        if not model: return None

        screen = np.array(ImageGrab.grab())
        screen_bgr = cv2.cvtColor(screen, cv2.COLOR_RGB2BGR)
        results = model(screen_bgr, conf=system.config['conf_threshold'], verbose=False)[0]
        
        for box in results.boxes:
            name = results.names[int(box.cls[0])]
            if name == target:
                bx, by, _, _ = box.xywh[0].tolist()
                return (int(bx), int(by))
        
        return None
    
class AIAutomation:
    def __init__(self, config):
        self.config = config
        self.all_classes, self.bg_classes, self.obj_classes = load_or_update_master_classes(config)
        self._model = None

    @property
    def model(self):
        if self._model is None and os.path.exists(self.config['model_path']):
            self._model = YOLO(self.config['model_path'])
        return self._model

    def find_and_click(self, target):
        """
        find_positionを使用して単一のターゲットを見つけ、クリックする
        """
        pos = find_position(target, self)
        if pos:
            x, y = pos
            ctypes.windll.user32.SetCursorPos(x, y)
            ctypes.windll.user32.mouse_event(2, 0, 0, 0, 0) # Down
            ctypes.windll.user32.mouse_event(4, 0, 0, 0, 0) # Up
            print(f"[*] Clicked '{target}': ({x}, {y})")
            return True
        else:
            print(f"[!] '{target}' が見つかりませんでした。")
            return False

    def capture_and_click(self, target_list):
        """
        target_listに含まれる要素（パス or クラス名）を順次クリック
        """
        if not self.model: 
            print("[!] モデルがありません。")
            return

        for item in target_list:
            # target_listが [("名前", 1), "パス"] などの形式に対応
            target = item[0] if isinstance(item, (list, tuple)) else item
            self.find_and_click(target)
            import time
            time.sleep(0.5)

    def run_file_sorting(self):
        run_auto_sorting(self.config, self.all_classes, self.bg_classes)

    def run_training_cycle(self):
        print("\n>>> 学習サイクル開始")
        if not self.bg_classes or not self.obj_classes:
            print("[!] bg_classes または obj_classes が空です。学習をスキップします。")
            print(f"    bg_classes : {self.bg_classes}")
            print(f"    obj_classes: {self.obj_classes}")
            print(f"    raw_bg_dir : {self.config['raw_bg_dir']}")
            print(f"    raw_obj_dir: {self.config['raw_obj_dir']}")
            return
        create_synthetic_data(self.config, self.all_classes, self.bg_classes, self.obj_classes)
        run_training(self.config)
        self._model = None

# ==========================================
# 副作用関数群の修正
# ==========================================

def run_live_visual_test(config, system):
    """実機ウィンドウ表示テスト: find_positionの動作確認"""
    print("\n>>> 【実機テスト】find_positionの動作を確認します")
    imgs = glob.glob(os.path.join(config['dataset_root'], "images/train/*.jpg"))
    if not imgs: return
    
    # テスト用画像をランダム表示
    test_img_path = random.choice(imgs)
    test_img = cv2.imread(test_img_path)
    win_name = "AI_VISUAL_TEST"
    cv2.namedWindow(win_name, cv2.WINDOW_AUTOSIZE)
    cv2.moveWindow(win_name, 100, 100)
    cv2.imshow(win_name, test_img)
    cv2.waitKey(1000)
    
    print("[*] 画像を表示しました。3秒後に認識テストを開始します。")
    import time
    time.sleep(3)

    # 1. クラス名でのテスト（適当な登録済みクラス名を取得）
    target_cls = system.all_classes[min(2, len(system.all_classes)-1)] 
    print(f"--- テスト1: クラス名 '{target_cls}' で探索 ---")
    system.find_and_click(target_cls)

    # 2. ファイルパスでのテスト（表示中の画像をそのままパス指定）
    print(f"--- テスト2: ファイルパス '{test_img_path}' で探索 ---")
    system.find_and_click(test_img_path)

    cv2.destroyAllWindows()

# ==========================================
# 4. メイン処理
# ==========================================

def main_process(config):
    system = AIAutomation(config)
    
    print("=== AI Image Recognition System (Test First Mode) ===")
    if os.path.exists(config['model_path']):
        print("\n>>> [STEP 0] 起動時実機テストを開始します")
        run_live_visual_test(config, system)
        
        # ついでに現在の設定での本番シーケンスも試したい場合はここで行う
        if input("\nそのまま本番シーケンスの動作確認を行いますか？ (y/n): ").lower() == 'y':
            target_sequence = [("Icon_放置少女V", 1), "酒", "1010_return","C:/Users/houch/Dropbox/Auto/AutoClick/Images/houchi/0000_account/0001/Click_0000ZZ_08.png"]
            system.capture_and_click(target_sequence)
    else:
        print("\n[!] モデルが存在しないため、初回学習へ進みます。")

    # ---------------------------------------------------------
    # 【設定・分別フェーズ】
    # ---------------------------------------------------------
    ans_sort = input("1. フォルダ分別を実行しますか？ (y/n): ").lower()
    train_mode = input("2. 学習モードを選択 (1:単発 / 2:目標精度ループ / 0:スキップ): ")
    
    target_accuracy = 95.0
    if train_mode == '2':
        val = input(f"   - 目標精度(%) [デフォルト: {target_accuracy}]: ")
        if val.strip(): 
            try: target_accuracy = float(val)
            except: pass

    # 分別実行
    if ans_sort == 'y':
        system.run_file_sorting()

    # YAML更新
    generate_data_yaml(config, system.all_classes)

    # ---------------------------------------------------------
    # 【長時間学習フェーズ】
    # ここからは時間がかかるので、ユーザーは離席してもOK
    # ---------------------------------------------------------
    if train_mode in ['1', '2']:
        print("\n>>> 長時間学習フェーズに移行します。終了後は自動で待機状態になります。")
        while True:
            system.run_training_cycle()
            current_acc = run_click_test(config)
            if train_mode == '1' or current_acc >= target_accuracy:
                print(f"\n[FINISH] 学習が完了しました。現在の内部精度: {current_acc:.2f}%")
                break
            print(f"[RETRY] 精度目標未達 ({current_acc:.2f}% < {target_accuracy}%)。再学習中...")

    print("\n[COMPLETE] すべての工程が終了しました。次回の起動時に新しいモデルでテストされます。")

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
        "master_list_path": "classes_master.txt", # マスタリストのファイル名
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