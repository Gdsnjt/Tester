# GigE Camera Tester

HarvesterライブラリでGigEカメラ接続をテストするプロジェクト

## 概要

このプロジェクトは、GigEカメラの接続・画像取得フローをテストするためのツールです。

- **モックモード**: 実カメラなしでフロー全体をテスト
- **Harvesterモード**: 実際のGigEカメラに接続

## ファイル構成

```
├── client.py              # GUIアプリケーション（メインエントリーポイント）
├── camera_interface.py    # カメラプロバイダー抽象インターフェース
├── harvester_camera.py    # 実カメラ用Harvester実装
├── mock_camera.py         # テスト用モックカメラ実装（内部シミュレーション）
├── gige_protocol.py       # GigE Vision プロトコル定義
├── gige_mock_server.py    # GigE Vision モックカメラサーバー
├── gige_client.py         # GigE Vision 直接クライアント
├── mock_camera_gui.py     # モックカメラサーバー GUI
├── test_gige_mock.py      # GigE モックサーバーテスト
├── ProducerGEV.cti        # GenTL Producer（実カメラ使用時に要配置）
└── requirements.txt       # 必要なライブラリ
```

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────┐
│                  client.py (GUI)                        │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│           camera_interface.py (抽象層)                  │
│               ICameraProvider                           │
└─────────────────────────────────────────────────────────┘
           │                │                │
    ┌──────┘                │                └──────┐
    ▼                       ▼                       ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│harvester_camera  │ │  mock_camera.py  │ │  gige_client.py  │
│   (実カメラ用)   │ │ (内部シミュレーション)│ │ (GigE直接接続)   │
│   Harvester使用  │ │  画像ファイル/生成 │ │  UDPプロトコル   │
└──────────────────┘ └──────────────────┘ └──────────────────┘
                                                   │
                                                   ▼
                                          ┌──────────────────┐
                                          │gige_mock_server  │
                                          │ (モックGigEカメラ)│
                                          │ 実際のネットワーク │
                                          └──────────────────┘
```

## セットアップ

### 1. ライブラリインストール

```bash
pip install -r requirements.txt
```

### 2. ProducerGEV.cti配置（実カメラ使用時のみ）

Basler pylonからコピー：
```powershell
Copy-Item "C:\Program Files\Basler\pylon 7\Runtime\x64\ProducerGEV.cti" ".\ProducerGEV.cti"
```

他のメーカーの場合は、対応するGenTL Producerをコピーしてください。

## 使い方

### 起動

```bash
python client.py
```

### モックモード（テスト・開発用）

1. 「モード選択」で「モック (テスト用)」を選択（デフォルト）
2. 「デバイス検出」をクリック
3. 検出されたモックカメラを選択して「接続」
4. 表示モードを選択:
   - **ライブビュー**: 「▶ ライブ開始」で連続表示
   - **単発撮影**: 「📷 撮影」で1枚ずつ取得
5. パラメータを変更して動作確認

**特徴:**
- 実カメラ・CTIファイル不要
- テスト用画像（グラデーション、チェッカーボード等）を自動生成
- 露光時間・ゲイン変更のシミュレーション
- 表示モード切り替え（ライブビュー/単発撮影）

### Harvesterモード（実カメラ用）

1. `ProducerGEV.cti` をプロジェクトフォルダに配置
2. GigEカメラを接続
3. 「モード選択」で「Harvester (実カメラ)」を選択
4. 「デバイス検出」でカメラを検出
5. カメラを選択して「接続」
6. 表示モードを選択:
   - **ライブビュー**: リアルタイム映像表示
   - **単発撮影**: 必要なタイミングで撮影

## GigE Vision モックカメラサーバー

実際のGigE Visionプロトコル（GVCP/GVSP）を実装したモックカメラサーバーです。
Harvesterなど、任意のGigE Vision対応クライアントからアクセスできます。

### 特徴

- **完全なGVCPサポート**: DISCOVERY、READREG、WRITEREG、READMEM
- **GVSPストリーミング**: 画像パケットの送信
- **カスタム画像対応**: 任意の画像をカメラ出力として使用可能
- **GUI制御**: GUIでサーバーを簡単に操作

### モックサーバー GUI の起動

```bash
python mock_camera_gui.py
```

### コマンドラインでの起動

```bash
# サーバー起動
python test_gige_mock.py --mode server

# クライアントテスト
python test_gige_mock.py --mode client

# サーバー＋クライアント統合テスト
python test_gige_mock.py --mode both
```

### プログラムからの使用（サーバー側）

```python
from gige_mock_server import GigEMockCameraServer, MockCameraConfig
import numpy as np

# 設定
config = MockCameraConfig(
    model_name="MyMockCamera",
    vendor_name="TestVendor",
    width=640,
    height=480
)

# サーバー作成
server = GigEMockCameraServer(config)

# カスタム画像を設定（オプション）
custom_image = np.zeros((480, 640, 3), dtype=np.uint8)
custom_image[:, :, 1] = 255  # 緑色
server.add_image(custom_image)

# 起動
if server.start():
    print(f"サーバー起動: {server.local_ip}:3956")
    # ... (サーバーを動作させる)
    server.stop()
```

### プログラムからの使用（クライアント側）

```python
from gige_client import GigEDirectProvider

# プロバイダー作成
provider = GigEDirectProvider()
provider.initialize()

# デバイス検出（ブロードキャスト）
devices = provider.discover_devices()

# または直接IPで接続
provider.connect("192.168.1.100", port=3956)

# 画像取得
provider.start_acquisition()
image = provider.get_image(timeout=5.0)
if image:
    print(f"取得: {image.width}x{image.height}")

# クリーンアップ
provider.stop_acquisition()
provider.disconnect()
provider.cleanup()
```

### ネットワークポートについて

- **GVCP**: UDP 3956（デフォルト）
- **GVSP**: 動的割り当て

他のGigEカメラと競合する場合は、カスタムポートを使用できます：

```python
# サーバー側
config = MockCameraConfig(gvcp_port=13956)

# クライアント側
provider.connect("192.168.1.100", port=13956)
```

## モックカメラの拡張

### カスタム画像を使用

```python
from mock_camera import MockCameraProvider

# 画像ファイルから
provider = MockCameraProvider(image_source="path/to/images/*.png")

# 動画ファイルから
provider = MockCameraProvider(image_source="path/to/video.mp4")

# ディレクトリから
provider = MockCameraProvider(image_source="path/to/image_folder/")
```

### プログラムからの使用

```python
from mock_camera import MockCameraProvider

# プロバイダー作成
provider = MockCameraProvider()
provider.initialize()

# デバイス検出
devices = provider.discover_devices()
print(f"検出: {devices}")

# 接続
provider.connect(0)

# 取得開始
provider.start_acquisition()

# 画像取得
for _ in range(10):
    image = provider.get_image()
    if image:
        print(f"Frame {image.frame_id}: {image.width}x{image.height}")

# クリーンアップ
provider.stop_acquisition()
provider.cleanup()
```

## 開発フレームワークとの統合

このプロジェクトの `ICameraProvider` インターフェースを使用することで、
開発フレームワークでモックとHarvesterを透過的に切り替えできます。

```python
from camera_interface import get_provider

# 自動選択（Harvesterが使えればHarvester、なければモック）
provider = get_provider(mode="auto")

# 明示的にモック
provider = get_provider(mode="mock")

# 明示的にHarvester
provider = get_provider(mode="harvester", cti_file="path/to/producer.cti")
```

## トラブルシューティング

### カメラが検出されない（Harvesterモード）

1. `ProducerGEV.cti` がプロジェクトフォルダにあるか確認
2. カメラがネットワークに接続されているか確認
3. ファイアウォールがGVCP (UDP 3956) をブロックしていないか確認
4. カメラのIPアドレスがPCと同じサブネットか確認

### Harvesterライブラリがインポートできない

```bash
pip install harvesters
```

### 画像が表示されない

1. カメラが正しく接続されているか確認
2. 「取得開始」ボタンを押したか確認
3. コンソールにエラーメッセージがないか確認

## ライセンス

MIT License
