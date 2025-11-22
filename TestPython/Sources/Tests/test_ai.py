import numpy as np
import time
from PIL import ImageGrab
import cv2
import gym
from gym import spaces
from pynput import mouse, keyboard
import torch
from stable_baselines3 import DQN # Deep Q-Networkを使用する場合
import pytk as tk

# --- 1. 定義 ---
mouse_ctrl = mouse.Controller()
kb_ctrl = keyboard.Controller()

# 定義可能な離散的な行動 (例: 10個の選択肢)
ACTION_MAP = {
    0: ('mouse_move_relative', 10, 0),    # 右に10px移動
    1: ('mouse_move_relative', -10, 0),   # 左に10px移動
    2: ('mouse_move_relative', 0, 10),    # 下に10px移動
    3: ('mouse_move_relative', 0, -10),   # 上に10px移動
    4: ('mouse_click', 'left'),           # 左クリック
    5: ('key_press', 'enter'),            # Enterキーを押す
    6: ('key_press', 'tab'),              # Tabキーを押す
    # ... 他の重要な操作 ...
    7: ('no_op', 0),                      # 何もしない
}

# --- 2. カスタム Gym 環境の作成 ---

class ScreenRPAEnv(gym.Env):
    """PC画面操作のためのカスタム強化学習環境"""
    metadata = {'render.modes': ['human']}

    def __init__(self):
        super(ScreenRPAEnv, self).__init__()

        # 状態空間: 画面キャプチャ (例: 84x84 グレースケール)
        self.observation_space = spaces.Box(
            low=0, high=255, shape=(1, 84, 84), dtype=np.uint8
        )
        
        # 行動空間: 定義された行動の数 (ACTION_MAPのサイズ)
        self.action_space = spaces.Discrete(len(ACTION_MAP))
        
        # 最終目標の座標 (例: 画面中央のボタン)
        self.target_area = (400, 400, 600, 600) 
        self.max_steps = 50 # 1エピソードの最大ステップ数
        self.current_step = 0

    def _get_observation(self):
        """現在の画面をキャプチャし、ニューラルネットワーク用に前処理する"""
        img = ImageGrab.grab()
        img_np = np.array(img)
        
        # グレースケールに変換し、リサイズ (DRLでよく使われる84x84)
        gray_img = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        resized_img = cv2.resize(gray_img, (84, 84), interpolation=cv2.INTER_AREA)
        
        # ネットワークの入力形式 (1, 84, 84) に整形し、正規化はモデルに任せる
        return np.expand_dims(resized_img, axis=0) 

    def _compute_reward(self):
        """報酬を計算するロジック (強化学習の鍵となる部分)"""
        
        # マウスが目標エリアに近づいたら報酬を与える
        x, y = mouse_ctrl.position
        
        # 目的のボタン上にマウスがある場合
        if self.target_area[0] < x < self.target_area[2] and \
           self.target_area[1] < y < self.target_area[3]:
            return 1.0 # 正の報酬
        else:
            return -0.01 # ステップごとにわずかな負の報酬 (早く目的を達成させるため)

    def step(self, action):
        """エージェントの行動を受け付け、次の状態、報酬、終了フラグを返す"""
        
        self.current_step += 1
        
        # 1. 行動の実行
        action_type, *params = ACTION_MAP[action]
        
        if action_type == 'mouse_move_relative':
            dx, dy = params
            x, y = mouse_ctrl.position
            mouse_ctrl.position = (x + dx, y + dy)
        elif action_type == 'mouse_click':
            # 実際にはクリック後に画面が変化するはず
            mouse_ctrl.click(mouse.Button.left, 1)
        elif action_type == 'key_press':
            key_val = params[0]
            if key_val == 'enter':
                 kb_ctrl.press(keyboard.Key.enter)
                 kb_ctrl.release(keyboard.Key.enter)
            # ... 他のキー操作 ...

        time.sleep(0.1) # 画面の変化を待つ

        # 2. 次の状態の取得
        observation = self._get_observation()
        
        # 3. 報酬の計算
        reward = self._compute_reward()
        
        # 4. エピソード終了判定
        done = self.current_step >= self.max_steps 
        # または、目的の操作が完了したかどうかを画面認識で判断
        
        info = {}
        return observation, reward, done, info

    def reset(self, **kwargs):
        """エピソード開始時に環境をリセットする"""
        self.current_step = 0
        # 実際のRPAでは、リセット時にウィンドウを初期状態に戻す操作が必要
        print("--- エピソード リセット ---") 
        return self._get_observation()

    def render(self, mode='human'):
        """人間が観察できるように環境を描画 (今回は不要だが、Gymの標準メソッド)"""
        pass

    def close(self):
        """環境を閉じる"""
        pass


# --- 3. 学習の実行 ---

def run_learning_with_drl():
    """強化学習エージェントをロードし、学習を実行する"""
    
    print("🧠 強化学習エージェントの初期化と学習を開始します...")
    
    # 1. 環境の作成
    env = ScreenRPAEnv()
    
    # 2. DRLモデルの定義 (PyTorchベースのDQN)
    # policy='CnnPolicy'を指定することで、画像入力に適した畳み込みニューラルネットワーク(CNN)を使用
    model = DQN("CnnPolicy", env, verbose=1, 
                learning_rate=1e-4, 
                buffer_size=10000, 
                learning_starts=1000,
                device="cuda" if torch.cuda.is_available() else "cpu")

    # 3. 学習の実行
    # ここでエージェントは画面キャプチャを状態として受け取り、最適な行動を学習します。
    # 実際のRPAでは、数百万ステップの学習が必要になる可能性があります。
    try:
        model.learn(total_timesteps=10000) 
    except Exception as e:
        print(f"学習中にエラーが発生しました: {e}")
        
    # 4. モデルの保存
    model.save("rpa_drl_model")
    print("💾 モデルを rpa_drl_model.zip に保存しました。")


# --- 4. 実行 (推論) の実行 ---

def run_execution_with_drl():
    """学習済みモデルをロードし、操作を実行する"""
    print("▶️ 学習済みモデルによる操作実行を開始します...")
    
    try:
        env = ScreenRPAEnv()
        # 1. モデルのロード
        model = DQN.load("rpa_drl_model", env=env)
        
        obs, _ = env.reset()
        done = False
        
        while not done:
            # 2. モデルによる行動選択 (推論)
            action, _states = model.predict(obs, deterministic=True)
            
            # 3. 行動の実行と次の状態へ
            obs, reward, done, info = env.step(action)
            
            print(f"行動: {ACTION_MAP[action]}, 報酬: {reward}, 終了: {done}")
            
    except FileNotFoundError:
        print("エラー: 学習済みモデル 'rpa_drl_model.zip' が見つかりません。")
    except Exception as e:
        print(f"実行中にエラーが発生しました: {e}")
        
    env.close()

# --- 5. GUI (ユーザーインターフェース) ---

def create_gui():
    """GUIウィンドウを作成する"""
    root = tk.Tk()
    root.title("DRL RPA ツール")
    root.geometry("350x180")
    
    lbl = tk.Label(root, text="強化学習モードを選択してください")
    lbl.pack(pady=10)
    
    # 学習ボタン
    btn_learn = tk.Button(root, text="🧠 学習モード (DRLで操作を学習)", command=run_learning_with_drl, height=2)
    btn_learn.pack(pady=5, padx=20, fill='x')
    
    # 実行ボタン
    btn_execute = tk.Button(root, text="▶️ 実行モード (学習済みモデルで操作)", command=run_execution_with_drl, height=2)
    btn_execute.pack(pady=5, padx=20, fill='x')
    
    root.mainloop()

if __name__ == "__main__":
    create_gui()