"""
モックカメラプロバイダー
テスト・開発用のシミュレーションカメラ実装
"""
import os
import glob
import threading
import time
from typing import List, Optional
import numpy as np
import cv2

from camera_interface import (
    ICameraProvider,
    CameraState,
    DeviceInfo,
    CameraParameters,
    ImageData
)


class MockCameraProvider(ICameraProvider):
    """
    モックカメラプロバイダー
    
    実カメラなしでHarvesterと同じインターフェースでテスト可能
    
    機能:
    - 生成画像（グラデーション、チェッカーボード、テストパターン）
    - 画像ファイル読み込み
    - 動画ファイル読み込み
    - フレームレート制御
    - パラメータ変更のシミュレーション
    
    使用方法:
        # 基本（生成画像）
        provider = MockCameraProvider()
        
        # 画像ファイルから
        provider = MockCameraProvider(image_source="path/to/images/*.png")
        
        # 動画ファイルから
        provider = MockCameraProvider(image_source="path/to/video.mp4")
    """
    
    def __init__(self, 
                 image_source: Optional[str] = None,
                 num_devices: int = 2,
                 frame_rate: float = 30.0):
        """
        Args:
            image_source: 画像ソース（ファイルパス、globパターン、動画パス、またはNone）
            num_devices: シミュレートするデバイス数
            frame_rate: フレームレート (fps)
        """
        super().__init__()
        
        self._image_source = image_source
        self._num_devices = num_devices
        self._target_frame_rate = frame_rate
        
        # 画像データ
        self._images: List[np.ndarray] = []
        self._current_image_index = 0
        self._video_capture: Optional[cv2.VideoCapture] = None
        
        # 取得制御
        self._acquisition_thread: Optional[threading.Thread] = None
        self._running = False
        self._frame_id = 0
        self._last_frame_time = 0.0
        
        # 遅延シミュレーション
        self._connect_delay = 0.5  # 接続遅延（秒）
        self._acquisition_delay = 0.1  # 取得開始遅延（秒）
    
    def initialize(self, **kwargs) -> bool:
        """
        プロバイダーを初期化
        
        Kwargs:
            image_source: 画像ソース（コンストラクタで指定していない場合）
            num_devices: シミュレートするデバイス数
        """
        try:
            # パラメータ更新
            if 'image_source' in kwargs:
                self._image_source = kwargs['image_source']
            if 'num_devices' in kwargs:
                self._num_devices = kwargs['num_devices']
            
            # 画像ソースをロード
            self._load_image_source()
            
            print(f"[Mock] 初期化完了: {len(self._images)}枚の画像")
            return True
            
        except Exception as e:
            print(f"[Mock] 初期化エラー: {e}")
            self._notify_error(e)
            return False
    
    def _load_image_source(self) -> None:
        """画像ソースをロード"""
        self._images = []
        
        if self._image_source is None:
            # デフォルト: テスト画像を生成
            self._generate_test_images()
            return
        
        # 動画ファイルの場合
        if self._image_source.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
            self._video_capture = cv2.VideoCapture(self._image_source)
            if not self._video_capture.isOpened():
                print(f"[Mock] 動画を開けません: {self._image_source}")
                self._video_capture = None
                self._generate_test_images()
            return
        
        # 画像ファイル/パターンの場合
        if '*' in self._image_source or '?' in self._image_source:
            # Globパターン
            files = sorted(glob.glob(self._image_source))
        elif os.path.isfile(self._image_source):
            # 単一ファイル
            files = [self._image_source]
        elif os.path.isdir(self._image_source):
            # ディレクトリ
            patterns = ['*.png', '*.jpg', '*.jpeg', '*.bmp', '*.tiff']
            files = []
            for pattern in patterns:
                files.extend(glob.glob(os.path.join(self._image_source, pattern)))
            files = sorted(files)
        else:
            files = []
        
        # 画像を読み込み
        for f in files:
            img = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                self._images.append(img)
        
        if not self._images:
            print(f"[Mock] 画像が見つかりません: {self._image_source}")
            self._generate_test_images()
    
    def _generate_test_images(self) -> None:
        """テスト用画像を生成"""
        width, height = 640, 480
        
        # 1. グラデーション
        img1 = np.zeros((height, width), dtype=np.uint8)
        for i in range(height):
            img1[i, :] = int(i * 255 / height)
        self._images.append(img1)
        
        # 2. チェッカーボード
        img2 = np.zeros((height, width), dtype=np.uint8)
        square_size = 40
        for i in range(0, height, square_size):
            for j in range(0, width, square_size):
                if ((i // square_size) + (j // square_size)) % 2 == 0:
                    img2[i:i+square_size, j:j+square_size] = 255
        self._images.append(img2)
        
        # 3. 同心円
        img3 = np.zeros((height, width), dtype=np.uint8)
        center = (width // 2, height // 2)
        for r in range(0, max(width, height), 20):
            cv2.circle(img3, center, r, (255 if (r // 20) % 2 == 0 else 128), 2)
        self._images.append(img3)
        
        # 4. テキスト情報
        img4 = np.ones((height, width), dtype=np.uint8) * 64
        cv2.putText(img4, "Mock Camera", (width//2 - 150, height//2 - 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.5, 255, 3)
        cv2.putText(img4, "Test Mode", (width//2 - 100, height//2 + 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, 200, 2)
        cv2.putText(img4, f"{width}x{height}", (width//2 - 60, height//2 + 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, 180, 2)
        self._images.append(img4)
        
        # 5. ノイズ画像
        img5 = np.random.randint(0, 256, (height, width), dtype=np.uint8)
        self._images.append(img5)
        
        # パラメータを更新
        self._parameters.width = width
        self._parameters.height = height
    
    def discover_devices(self) -> List[DeviceInfo]:
        """デバイスを検出（シミュレーション）"""
        # 接続遅延をシミュレート
        time.sleep(0.2)
        
        self._devices = []
        for i in range(self._num_devices):
            device = DeviceInfo(
                index=i,
                vendor="MockCam Corp",
                model=f"VirtualCam-{i+1}",
                serial_number=f"MOCK{i+1:03d}",
                user_defined_name=f"TestCamera_{i+1}"
            )
            self._devices.append(device)
        
        print(f"[Mock] {len(self._devices)}台のデバイスを検出")
        return self._devices
    
    def connect(self, device_index: int) -> bool:
        """指定デバイスに接続（シミュレーション）"""
        if device_index < 0 or device_index >= len(self._devices):
            print(f"[Mock] 無効なデバイスインデックス: {device_index}")
            return False
        
        try:
            # 接続遅延をシミュレート
            time.sleep(self._connect_delay)
            
            self._current_device = self._devices[device_index]
            self._state = CameraState.CONNECTED
            
            # パラメータを設定
            if self._images:
                self._parameters.height, self._parameters.width = self._images[0].shape[:2]
            
            print(f"[Mock] 接続完了: {self._current_device}")
            return True
            
        except Exception as e:
            print(f"[Mock] 接続エラー: {e}")
            self._notify_error(e)
            return False
    
    def disconnect(self) -> bool:
        """接続を切断"""
        try:
            if self._state == CameraState.ACQUIRING:
                self.stop_acquisition()
            
            self._current_device = None
            self._state = CameraState.DISCONNECTED
            
            print("[Mock] 切断完了")
            return True
            
        except Exception as e:
            print(f"[Mock] 切断エラー: {e}")
            return False
    
    def start_acquisition(self) -> bool:
        """画像取得を開始"""
        if self._state != CameraState.CONNECTED:
            return False
        
        try:
            # 開始遅延をシミュレート
            time.sleep(self._acquisition_delay)
            
            self._state = CameraState.ACQUIRING
            self._frame_id = 0
            self._last_frame_time = time.time()
            
            print("[Mock] 取得開始")
            return True
            
        except Exception as e:
            print(f"[Mock] 取得開始エラー: {e}")
            self._notify_error(e)
            return False
    
    def stop_acquisition(self) -> bool:
        """画像取得を停止"""
        try:
            self._running = False
            
            if self._acquisition_thread is not None:
                self._acquisition_thread.join(timeout=2.0)
                self._acquisition_thread = None
            
            if self._state == CameraState.ACQUIRING:
                self._state = CameraState.CONNECTED
            
            print("[Mock] 取得停止")
            return True
            
        except Exception as e:
            print(f"[Mock] 取得停止エラー: {e}")
            return False
    
    def get_image(self, timeout: float = 1.0) -> Optional[ImageData]:
        """画像を1枚取得"""
        if self._state != CameraState.ACQUIRING:
            return None
        
        try:
            # フレームレート制御
            frame_interval = 1.0 / self._target_frame_rate
            elapsed = time.time() - self._last_frame_time
            if elapsed < frame_interval:
                time.sleep(frame_interval - elapsed)
            
            self._last_frame_time = time.time()
            
            # 画像を取得
            if self._video_capture is not None:
                # 動画から
                ret, frame = self._video_capture.read()
                if not ret:
                    # ループ再生
                    self._video_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = self._video_capture.read()
                
                if ret:
                    if len(frame.shape) == 3:
                        image = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    else:
                        image = frame
                else:
                    return None
            else:
                # 静止画リストから
                if not self._images:
                    return None
                
                image = self._images[self._current_image_index].copy()
                self._current_image_index = (self._current_image_index + 1) % len(self._images)
            
            # 露光時間に応じた明るさ調整（シミュレーション）
            brightness_factor = self._parameters.exposure_time / 10000.0
            brightness_factor = np.clip(brightness_factor, 0.5, 2.0)
            image = np.clip(image * brightness_factor, 0, 255).astype(np.uint8)
            
            # ゲインに応じたノイズ追加（シミュレーション）
            if self._parameters.gain > 0:
                noise_level = self._parameters.gain * 0.5
                noise = np.random.normal(0, noise_level, image.shape).astype(np.int16)
                image = np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)
            
            # タイムスタンプとフレーム番号を画像に描画（オプション）
            self._frame_id += 1
            timestamp = time.time()
            
            # フレーム情報をオーバーレイ
            overlay = image.copy()
            info_text = f"Frame: {self._frame_id}  Time: {timestamp:.3f}"
            cv2.putText(overlay, info_text, (10, 25), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, 255, 1)
            cv2.putText(overlay, f"Exp: {self._parameters.exposure_time:.0f}us  Gain: {self._parameters.gain:.1f}dB",
                       (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 200, 1)
            
            return ImageData(
                data=overlay,
                width=overlay.shape[1],
                height=overlay.shape[0],
                timestamp=timestamp,
                frame_id=self._frame_id,
                pixel_format="Mono8"
            )
            
        except Exception as e:
            print(f"[Mock] 画像取得エラー: {e}")
            self._notify_error(e)
            return None
    
    def set_exposure_time(self, value: float) -> bool:
        """露光時間を設定"""
        # 範囲チェック
        value = np.clip(value, self._parameters.exposure_min, self._parameters.exposure_max)
        self._parameters.exposure_time = value
        print(f"[Mock] 露光時間設定: {value} μs")
        return True
    
    def set_gain(self, value: float) -> bool:
        """ゲインを設定"""
        # 範囲チェック
        value = np.clip(value, self._parameters.gain_min, self._parameters.gain_max)
        self._parameters.gain = value
        print(f"[Mock] ゲイン設定: {value} dB")
        return True
    
    def cleanup(self) -> None:
        """リソースを解放"""
        try:
            self.disconnect()
            
            if self._video_capture is not None:
                self._video_capture.release()
                self._video_capture = None
            
            self._images = []
            
            print("[Mock] クリーンアップ完了")
            
        except Exception as e:
            print(f"[Mock] クリーンアップエラー: {e}")
    
    # === モック固有のメソッド ===
    
    def set_connect_delay(self, delay: float) -> None:
        """接続遅延を設定（テスト用）"""
        self._connect_delay = delay
    
    def set_acquisition_delay(self, delay: float) -> None:
        """取得開始遅延を設定（テスト用）"""
        self._acquisition_delay = delay
    
    def add_image(self, image: np.ndarray) -> None:
        """画像を追加"""
        if len(image.shape) == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        self._images.append(image.copy())
    
    def clear_images(self) -> None:
        """画像をクリア"""
        self._images = []
        self._current_image_index = 0
    
    def simulate_error(self, error_type: str = "timeout") -> None:
        """エラーをシミュレート（テスト用）"""
        if error_type == "timeout":
            raise TimeoutError("Simulated timeout error")
        elif error_type == "disconnect":
            self._state = CameraState.DISCONNECTED
            raise ConnectionError("Simulated disconnect error")
        else:
            raise RuntimeError(f"Simulated error: {error_type}")


# === テスト実行 ===
if __name__ == "__main__":
    print("=== MockCameraProvider テスト ===\n")
    
    # プロバイダー作成
    provider = MockCameraProvider()
    
    # 初期化
    if not provider.initialize():
        print("初期化失敗")
        exit(1)
    
    # デバイス検出
    devices = provider.discover_devices()
    print(f"\n検出デバイス:")
    for dev in devices:
        print(f"  {dev}")
    
    # 接続
    if devices:
        print(f"\n最初のデバイスに接続...")
        if provider.connect(0):
            print(f"接続成功: {provider.current_device}")
            print(f"パラメータ: {provider.parameters}")
            
            # 取得開始
            print("\n画像取得テスト...")
            provider.start_acquisition()
            
            for i in range(5):
                image = provider.get_image()
                if image:
                    print(f"  Frame {image.frame_id}: {image.width}x{image.height}, "
                          f"timestamp={image.timestamp:.3f}")
            
            # 取得停止
            provider.stop_acquisition()
    
    # クリーンアップ
    provider.cleanup()
    print("\nテスト完了")
