"""
GigE Visionモックカメラ テスト
モックサーバーとクライアントの接続テスト
"""
import sys
import time
import threading
import numpy as np
import cv2


def test_mock_server():
    """モックサーバーのみを起動"""
    from gige_mock_server import GigEMockCameraServer, MockCameraConfig
    from gige_protocol import PixelFormat
    
    print("=" * 60)
    print("GigE Vision モックカメラサーバー テスト")
    print("=" * 60)
    
    # 設定
    config = MockCameraConfig(
        vendor="Test Vendor",
        model="Test Camera",
        serial_number="TEST001",
        width=640,
        height=480,
        pixel_format=PixelFormat.BGR8,
        frame_rate=30.0
    )
    
    # サーバー起動
    server = GigEMockCameraServer(config=config)
    
    if server.start():
        print(f"サーバーを起動しました: {server.local_ip}:3956")
        print("Ctrl+C で終了...")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n終了中...")
        finally:
            server.stop()
    else:
        print("サーバーの起動に失敗しました")


def test_client_only(server_ip: str = ""):
    """クライアントのみでテスト（外部サーバーに接続）"""
    from gige_client import GigEVisionClient
    
    print("=" * 60)
    print("GigE Vision クライアント テスト")
    print("=" * 60)
    
    client = GigEVisionClient()
    
    # デバイス検出
    print("\nデバイスを検出中...")
    devices = client.discover_devices(timeout=3.0)
    
    if not devices:
        print("デバイスが見つかりませんでした")
        return
    
    print(f"\n{len(devices)} 台のデバイスを検出:")
    for i, dev in enumerate(devices):
        print(f"  [{i}] {dev.model} ({dev.vendor})")
        print(f"      IP: {dev.ip}, Serial: {dev.serial_number}")
    
    # 接続
    if server_ip:
        target = server_ip
    else:
        target = devices[0].ip
    
    print(f"\n{target} に接続中...")
    if client.connect(target):
        print("接続成功!")
        
        # 取得開始
        print("\n画像取得開始...")
        client.start_acquisition()
        
        time.sleep(1)
        
        # 画像取得
        print("画像取得中...")
        for i in range(5):
            image = client.capture()
            if image is not None:
                print(f"  画像 {i+1}: {image.shape}")
            else:
                print(f"  画像 {i+1}: 取得失敗")
            time.sleep(0.5)
        
        # 停止
        client.stop_acquisition()
        client.disconnect()
        print("\n接続を終了しました")
    else:
        print("接続に失敗しました")


def test_server_and_client():
    """サーバーとクライアントの統合テスト"""
    from gige_mock_server import GigEMockCameraServer, MockCameraConfig
    from gige_client import GigEVisionClient
    from gige_protocol import PixelFormat
    
    print("=" * 60)
    print("GigE Vision 統合テスト (サーバー + クライアント)")
    print("=" * 60)
    
    # サーバー設定（別のポートを使用してネットワーク上の他のカメラとの競合を避ける）
    TEST_PORT = 13956  # 標準の3956の代わりに使用
    
    config = MockCameraConfig(
        vendor="Test Vendor",
        model="Test Camera",
        serial_number="INTEG001",
        width=160,  # テスト用に小さいサイズ
        height=120,
        pixel_format=PixelFormat.BGR8,
        frame_rate=5.0,  # テスト用に低フレームレート
        gvcp_port=TEST_PORT  # テスト用ポート
    )
    
    # サーバー起動
    print("\n[1] サーバーを起動中...")
    server = GigEMockCameraServer(config=config)
    server._heartbeat_timeout = 30000  # テスト用に30秒に延長
    
    # サーバー起動
    print("\n[1] サーバーを起動中...")
    server = GigEMockCameraServer(config=config)
    
    if not server.start():
        print("サーバーの起動に失敗しました")
        return False
    
    server_ip = server.local_ip
    print(f"    サーバー起動完了: {server_ip}:3956")
    
    time.sleep(1)
    
    # クライアントテスト
    print("\n[2] クライアントを作成・初期化...")
    client = GigEVisionClient()
    if not client.initialize():
        print("    クライアントの初期化に失敗しました")
        server.stop()
        return False
    
    # デバイス検出
    print("\n[3] デバイスを検出中...")
    devices = client.discover_devices(timeout=2.0)
    
    if not devices:
        print("    デバイスが見つかりませんでした")
        # 直接接続を試みる
        print(f"    直接接続を試みます: {server_ip}")
    else:
        print(f"    {len(devices)} 台のデバイスを検出:")
        for dev in devices:
            print(f"      - {dev.model} ({dev.vendor})")
    
    # 接続（テスト用ポートを指定）
    print(f"\n[4] {server_ip}:{TEST_PORT} に接続中...")
    if not client.connect(server_ip, port=TEST_PORT):
        print("    接続に失敗しました")
        client.cleanup()
        server.stop()
        return False
    
    print("    接続成功!")
    
    # 取得開始
    print("\n[5] 画像取得開始...")
    client.start_acquisition()
    
    time.sleep(0.5)
    
    # 画像取得
    print("\n[6] 画像取得中...")
    success_count = 0
    for i in range(5):
        image = client.capture(timeout=2.0)
        if image is not None:
            print(f"    画像 {i+1}: {image.shape} - 成功")
            success_count += 1
        else:
            print(f"    画像 {i+1}: タイムアウト")
        time.sleep(0.3)
    
    # カスタム画像テスト
    print("\n[7] カスタム画像テスト...")
    custom_image = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(custom_image, "CUSTOM IMAGE", (150, 240),
                cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 4)
    server.set_image(custom_image)
    
    time.sleep(0.5)
    
    image = client.capture(timeout=2.0)
    if image is not None:
        print(f"    カスタム画像を受信: {image.shape}")
        # 緑色チェック
        green_pixels = np.sum(image[:, :, 1] > 200)
        if green_pixels > 1000:
            print("    カスタム画像の検証: 成功 (緑色ピクセルを検出)")
            success_count += 1
        else:
            print("    カスタム画像の検証: 警告 (緑色ピクセルが少ない)")
    else:
        print("    カスタム画像の取得に失敗")
    
    # 停止
    print("\n[8] 終了処理...")
    client.stop_acquisition()
    client.disconnect()
    server.stop()
    
    # 結果
    print("\n" + "=" * 60)
    print(f"テスト結果: {success_count}/{6} 成功")
    print("=" * 60)
    
    return success_count >= 4


def test_with_harvester():
    """Harvesterを使ったテスト（参考用）"""
    print("=" * 60)
    print("Harvester テスト")
    print("=" * 60)
    
    try:
        from harvesters.core import Harvester
        
        h = Harvester()
        
        # CTIファイルを検索
        import os
        cti_file = None
        current_dir = os.path.dirname(os.path.abspath(__file__))
        for f in os.listdir(current_dir):
            if f.endswith('.cti'):
                cti_file = os.path.join(current_dir, f)
                break
        
        if cti_file:
            print(f"CTIファイル: {cti_file}")
            h.add_file(cti_file)
            h.update()
            
            print(f"\n検出されたデバイス: {len(h.device_info_list)}")
            for info in h.device_info_list:
                print(f"  - {info.model}")
                print(f"    Vendor: {info.vendor}")
                print(f"    Serial: {info.serial_number}")
            
            h.reset()
        else:
            print("CTIファイルが見つかりません")
        
        print("\n注意: Harvesterは通常、ソフトウェアモックカメラを検出できません")
        print("      代わりに gige_client.py を使用してください")
        
    except ImportError:
        print("Harvestersがインストールされていません")
        print("pip install harvesters")
    except Exception as e:
        print(f"エラー: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="GigE Visionテスト")
    parser.add_argument("--mode", "-m", 
                       choices=["server", "client", "both", "harvester"],
                       default="both",
                       help="テストモード")
    parser.add_argument("--ip", "-i", default="",
                       help="接続先サーバーIP（クライアントモード時）")
    args = parser.parse_args()
    
    if args.mode == "server":
        test_mock_server()
    elif args.mode == "client":
        test_client_only(args.ip)
    elif args.mode == "both":
        test_server_and_client()
    elif args.mode == "harvester":
        test_with_harvester()


if __name__ == "__main__":
    main()
