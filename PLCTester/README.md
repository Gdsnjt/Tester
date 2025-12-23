# 三菱PLC テスター

MCプロトコルに対応した三菱PLCのモックサーバーとテストクライアント。
外部ライブラリを使用せず、Python標準ライブラリのみで実装。

## 機能

### 対応シリーズ
- **Qシリーズ**: 3Eフレーム対応
- **iQ-Rシリーズ**: 4Eフレーム対応

### 対応デバイス
| カテゴリ | デバイス | 説明 |
|---------|---------|------|
| ビット | M | 内部リレー |
| ビット | L | ラッチリレー |
| ビット | B | リンクリレー |
| ビット | X | 入力 |
| ビット | Y | 出力 |
| ビット | F | アナンシエータ |
| ビット | V | エッジリレー |
| ビット | S | ステップリレー |
| ビット | TC | タイマ接点 |
| ビット | TS | タイマコイル |
| ビット | CC | カウンタ接点 |
| ビット | CS | カウンタコイル |
| ビット | SM | 特殊リレー |
| ビット | SB | リンク特殊リレー |
| ワード | D | データレジスタ |
| ワード | W | リンクレジスタ |
| ワード | R | ファイルレジスタ |
| ワード | ZR | 拡張ファイルレジスタ |
| ワード | TN | タイマ現在値 |
| ワード | CN | カウンタ現在値 |
| ワード | SD | 特殊レジスタ |
| ワード | SW | リンク特殊レジスタ |
| ワード | Z | インデックスレジスタ |

### 対応コマンド
- 一括読出し / 一括書込み
- CPU型名読出し
- リモートRUN / STOP / PAUSE / RESET

## ファイル構成

```
PLCTester/
├── mc_protocol.py      # MCプロトコル実装
├── plc_devices.py      # デバイス管理
├── ladder_engine.py    # ラダー回路エンジン
├── ladder_gxworks.py   # GX Works2互換ラダー記述
├── mock_plc_server.py  # モックPLCサーバー
├── plc_client.py       # PLCクライアント
├── server_gui.py       # サーバーGUI（別プロセス）
├── client_gui.py       # クライアントGUI（別プロセス）
├── gui.py              # 統合GUI（旧版）
└── README.md           # このファイル
```

## 使用方法

### サーバーとクライアントを別々に起動（推奨）

実際の開発環境では、PLCサーバーとクライアントアプリケーションを
別プロセスで動作させてテストします。

#### 1. サーバー起動

```bash
python server_gui.py
```

**サーバーGUIの操作手順:**

1. 「サーバー起動」ボタンをクリック
2. ラダープログラムタブでプログラムをロード
   - サンプルプログラム選択
   - GX Works2形式テキストファイルからロード
   - エディタで直接記述
3. 「RUN」ボタンでラダープログラム実行開始
4. デバイス状態タブでモニタ・直接操作

#### 2. クライアント起動（別ターミナル）

```bash
python client_gui.py
```

**クライアントGUIの操作手順:**

1. 接続設定でホスト・ポートを確認
2. 「接続」ボタンでPLCに接続
3. デバイス読み書きタブ:
   - デバイスを選択して読み取り/書き込み
   - クイック操作ボタンで入力ON/OFF
4. デバイスモニタタブ:
   - モニタ対象を追加（プリセットボタンで簡単追加）
   - 「モニタ開始」でリアルタイム監視
5. PLC制御タブ:
   - リモートRUN/STOP/RESET

### GX Works2形式ラダー記述

サーバーGUIでは、GX Works2に似た形式でラダープログラムを記述できます。

```
; ネットワーク1 - 自己保持回路
NETWORK 1
COMMENT 起動スイッチと停止スイッチ
LD X0
OR Y0
ANI X1
OUT Y0

; ネットワーク2 - タイマ回路
NETWORK 2
COMMENT 3秒タイマ
LD X2
OUT T0 K30

; ネットワーク3 - タイマ出力
NETWORK 3
LD T0
OUT Y1

END
```

**対応命令:**
- 接点: LD, LDI, AND, ANI, OR, ORI
- 出力: OUT, SET, RST
- タイマ/カウンタ: OUT (T, C)
- データ転送: MOV
- 演算: ADD, SUB, MUL, DIV
- K定数、H定数対応

### 統合GUI（旧版）

```bash
python gui.py
```

#### 基本的な操作手順

1. **サーバー起動**
   - 「サーバー起動」ボタンをクリック
   - モックPLCが起動します

2. **ラダープログラムロード**
   - ドロップダウンからプログラムを選択
   - 「ロード」ボタンをクリック

3. **クライアント接続**
   - 「接続」ボタンをクリック
   - モックPLCに接続します

4. **リモート制御**
   - 「RUN」でPLC実行開始
   - 「STOP」で停止
   - 「RESET」でリセット

5. **デバイス操作**
   - デバイス名（例: D0, M0）を入力
   - 「ワード読出し」「ビット読出し」で値を確認
   - 値を入力して「ワード書込み」「ビット書込み」で設定

6. **モニター**
   - モニタ対象デバイスを入力（カンマ区切り）
   - 「モニタ開始」で定期監視

### プログラムからの使用

#### クライアントの使用

```python
from plc_client import PLCClient, ConnectionConfig
from mc_protocol import PLCSeries

# 設定
config = ConnectionConfig(
    host="127.0.0.1",
    port=5000,
    series=PLCSeries.Q_SERIES
)

# 接続
client = PLCClient(config)
client.connect()

# デバイス読み書き
value = client.read_word("D", 0)
print(f"D0 = {value}")

client.write_word("D", 100, 1234)

bits = client.read_bits("M", 0, 10)
print(f"M0-M9 = {bits}")

client.write_bit("Y", 0, True)

# CPU型名読出し
model = client.read_cpu_model()
print(f"CPU: {model}")

# リモート制御
client.remote_run()
client.remote_stop()

# 切断
client.disconnect()
```

#### with文の使用

```python
with PLCClient(config) as client:
    client.write_word("D", 0, 100)
    value = client.read_word("D", 0)
```

### ラダープログラムの作成

```python
from ladder_engine import LadderProgram

# 自己保持回路
program = LadderProgram("自己保持回路")
program.LD("X0")       # X0がONで
program.OR("Y0")       # または Y0がONで
program.ANI("X1")      # かつ X1がOFFなら
program.OUT("Y0")      # Y0をON
program.END()

# タイマ回路
program2 = LadderProgram("タイマ回路")
program2.LD("X0")
program2.OUT_T(0, 20)  # T0, 2秒（設定値 x 100ms）
program2.LD("TC0")     # タイマ接点
program2.OUT("Y0")
program2.END()

# カウンタ回路
program3 = LadderProgram("カウンタ回路")
program3.LD("X0")
program3.OUT_C(0, 5)   # C0, 5カウント
program3.LD("CC0")     # カウンタ接点
program3.OUT("Y0")
program3.LD("X1")
program3.RST_C(0)      # カウンタリセット
program3.END()

# 演算
program4 = LadderProgram("演算")
program4.LD("M0")
program4.MOV(100, "D0")        # D0 = 100
program4.ADD("D0", "D1", "D2") # D2 = D0 + D1
program4.SUB("D0", 10, "D3")   # D3 = D0 - 10
program4.MUL("D0", 2, "D4")    # D4 = D0 * 2
program4.DIV("D0", 3, "D5")    # D5 = D0 / 3
program4.END()
```

### 利用可能なラダー命令

| 命令 | 説明 | 例 |
|------|------|-----|
| LD | a接点ロード | `LD("X0")` |
| LDI | b接点ロード | `LDI("X1")` |
| AND | a接点直列 | `AND("M0")` |
| ANI | b接点直列 | `ANI("M1")` |
| OR | a接点並列 | `OR("X2")` |
| ORI | b接点並列 | `ORI("X3")` |
| ANB | ブロック直列 | `ANB()` |
| ORB | ブロック並列 | `ORB()` |
| MPS | プッシュ | `MPS()` |
| MRD | リード | `MRD()` |
| MPP | ポップ | `MPP()` |
| OUT | 出力 | `OUT("Y0")` |
| SET | セット | `SET("M0")` |
| RST | リセット | `RST("M0")` |
| PLS | パルス（立上り） | `PLS("M10")` |
| PLF | パルス（立下り） | `PLF("M11")` |
| OUT_T | タイマ出力 | `OUT_T(0, 10)` |
| OUT_C | カウンタ出力 | `OUT_C(0, 5)` |
| RST_T | タイマリセット | `RST_T(0)` |
| RST_C | カウンタリセット | `RST_C(0)` |
| MOV | 転送 | `MOV(100, "D0")` |
| ADD | 加算 | `ADD("D0", "D1", "D2")` |
| SUB | 減算 | `SUB("D0", 10, "D1")` |
| MUL | 乗算 | `MUL("D0", 2, "D1")` |
| DIV | 除算 | `DIV("D0", 3, "D1")` |
| END | 終了 | `END()` |

## サーバーの直接使用

```python
from mock_plc_server import MockPLCServer
from mc_protocol import PLCSeries
from ladder_engine import create_sample_program_1

# サーバー作成
server = MockPLCServer(
    host="127.0.0.1",
    port=5000,
    series=PLCSeries.Q_SERIES
)

# ラダープログラムロード
server.load_ladder_program(create_sample_program_1())

# 起動
server.start()

# デバイス操作（サーバー側）
server.set_device_value("X", 0, 1)  # X0をON
value = server.get_device_value("Y", 0)  # Y0を読出し

# 停止
server.stop()
```

## 接続・切断テスト

```python
from plc_client import PLCClient, ConnectionConfig, PLCClientError

config = ConnectionConfig(host="127.0.0.1", port=5000)

# 接続テスト
try:
    client = PLCClient(config)
    client.connect()
    print("接続成功")
    
    # 通信テスト
    if client.test_connection():
        print("通信OK")
    
    client.disconnect()
    print("切断成功")
    
except PLCClientError as e:
    print(f"エラー: {e}")
    print(f"エラーコード: {e.error_code}")
```

## 注意事項

- モックサーバーはテスト目的のみ使用してください
- 実機への接続時は適切な安全対策を講じてください
- タイマ精度はスキャンタイム（デフォルト10ms）に依存します

## ライセンス

MIT License
