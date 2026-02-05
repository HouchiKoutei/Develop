# 画像・動画 自動分類AI 動作仕様書

### システム概要
本システムは、YOLOv8をベースとした物体検出AIであり、フォルダ構成からの自動設定生成、背景合成による学習データ自動作成、および学習・推論の動的切り替え機能を備えた「自ら育てるAI」プラットフォームである。

### 起動モード管理仕様
システムの起動状態やスコア状況に応じて、以下の3つのモードを自動的に切り替える。

1. **初期学習モード（初回起動）**
   - 学習済みモデル（`best.pt`）が存在しない場合に実行。
   - `data.yaml`の自動生成、合成データの作成、新規トレーニングを順次行う。

2. **推論実行モード（通常起動）**
   - すでに学習済みモデルが存在する場合に実行。
   - 保存された重みファイルをロードし、入力画像・動画に対して物体検出、個数カウント、位置特定、背景分類を行う。

3. **リカバリ学習モード（条件分岐）**
   - 開始時得点が「0」になった場合、即座に推論を停止し、残りのステップ数を学習プロセス（データの再精査や追加学習）に割り当てる。

### データ処理仕様
- **設定自動生成:** `dataset/images/train/`配下のフォルダ名をクラス名として自動抽出。
- **データ増幅:** 背景透過PNG（Object）と風景写真（Background）をランダムなスケール・位置で合成。
- **解析出力:** 検出物の中心座標（クリック判定用）、種類別カウント、背景特定をJSON形式で構造化。

### 設定パラメータ（Dictionary構造）
システム全体を以下の辞書データ（Config）で制御する。
- **パス設定:** `dataset_root`, `model_path`, `raw_materials` 等
- **学習設定:** `num_synth_images`, `epochs`, `batch_size` 等
- **判定閾値:** `bg_threshold`（背景判定面積比）, `click_radius` 等
- **運用変数:** `initial_score`（開始時得点）, `total_steps`（終了ステップ数）

### 制御フローチャート
```mermaid
graph TD

    subgraph "Main_Process"
        START["システム起動"] --> LOAD_CONFIG["設定Dictionary<br/>読み込み"]
        LOAD_CONFIG --> CHECK_MODEL{"学習済みモデル<br/>(best.pt)の確認"}
    end

    subgraph "Mode_Decision"
        CHECK_MODEL -- "存在しない" --> MODE_TRAIN["①学習モード起動"]
        CHECK_MODEL -- "存在する" --> CHECK_SCORE{"開始時得点の判定"}
        
        CHECK_SCORE -- "得点 > 0" --> MODE_INFER["②推論モード起動"]
        CHECK_SCORE -- "得点 = 0" --> MODE_RECOVERY["③リカバリ学習<br/>モード起動"]
    end

    subgraph "Action_Details"
        MODE_TRAIN --> GEN_YAML["data.yaml<br/>自動生成"]
        GEN_YAML --> GEN_DATA["合成画像による<br/>データ増幅実行"]
        GEN_DATA --> EXEC_TRAIN["YOLOトレーニング<br/>開始"]

        MODE_INFER --> EXEC_INFER["推論・物体検出<br/>(位置/数/背景取得)"]
        EXEC_INFER --> STEP_DECR["ステップ数消費<br/>(Step - 1)"]
        STEP_DECR --> CHECK_FINISH{"全ステップ終了<br/>または得点=0"}

        MODE_RECOVERY --> SWAP_TRAIN["推論停止・残ステップ<br/>を学習へ転換"]
        SWAP_TRAIN --> EXEC_TRAIN
    end

    subgraph "Output_Result"
        CHECK_FINISH -- "終了" --> SAVE_ALL["結果保存<br/>(JSON/画像)"]
        CHECK_FINISH -- "継続" --> CHECK_SCORE
        EXEC_TRAIN --> END["プロセス終了"]
        SAVE_ALL --> END
    end

    %% スタイリング
    style START fill:#f9f,stroke:#333
    style END fill:#f9f,stroke:#333
    style MODE_TRAIN fill:#fff4dd,stroke:#d4a017
    style MODE_INFER fill:#e1f5fe,stroke:#01579b
    style MODE_RECOVERY fill:#ffebee,stroke:#c62828