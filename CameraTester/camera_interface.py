"""
カメラプロバイダー抽象インターフェース
Harvester実装とモック実装を統一的に扱うための基底クラス
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Callable
from enum import Enum
import numpy as np


class CameraState(Enum):
    """カメラの状態"""
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    ACQUIRING = "acquiring"


@dataclass
class DeviceInfo:
    """検出されたデバイス情報"""
    index: int
    vendor: str
    model: str
    serial_number: str
    user_defined_name: str = ""
    
    def __str__(self) -> str:
        name = self.user_defined_name or self.model
        return f"{self.vendor} {name} (SN: {self.serial_number})"


@dataclass 
class CameraParameters:
    """カメラパラメータ"""
    width: int = 640
    height: int = 480
    pixel_format: str = "Mono8"
    exposure_time: float = 10000.0  # μs
    gain: float = 0.0  # dB
    frame_rate: float = 30.0  # fps
    
    # パラメータの範囲（読み取り専用情報）
    exposure_min: float = 10.0
    exposure_max: float = 1000000.0
    gain_min: float = 0.0
    gain_max: float = 24.0


@dataclass
class ImageData:
    """取得画像データ"""
    data: np.ndarray
    width: int
    height: int
    timestamp: float
    frame_id: int
    pixel_format: str = "Mono8"


class ICameraProvider(ABC):
    """
    カメラプロバイダー抽象基底クラス
    
    実装クラス:
    - HarvesterCameraProvider: 実カメラ用 (Harvesterライブラリ使用)
    - MockCameraProvider: テスト用 (画像ファイル/生成画像)
    """
    
    def __init__(self):
        self._state = CameraState.DISCONNECTED
        self._devices: List[DeviceInfo] = []
        self._current_device: Optional[DeviceInfo] = None
        self._parameters = CameraParameters()
        self._frame_callback: Optional[Callable[[ImageData], None]] = None
        self._error_callback: Optional[Callable[[Exception], None]] = None
    
    @property
    def state(self) -> CameraState:
        """現在の状態を取得"""
        return self._state
    
    @property
    def is_connected(self) -> bool:
        """接続中かどうか"""
        return self._state in (CameraState.CONNECTED, CameraState.ACQUIRING)
    
    @property
    def is_acquiring(self) -> bool:
        """取得中かどうか"""
        return self._state == CameraState.ACQUIRING
    
    @property
    def devices(self) -> List[DeviceInfo]:
        """検出されたデバイスリスト"""
        return self._devices
    
    @property
    def current_device(self) -> Optional[DeviceInfo]:
        """現在接続中のデバイス"""
        return self._current_device
    
    @property
    def parameters(self) -> CameraParameters:
        """カメラパラメータ"""
        return self._parameters
    
    def set_frame_callback(self, callback: Callable[[ImageData], None]) -> None:
        """フレーム受信時のコールバックを設定"""
        self._frame_callback = callback
    
    def set_error_callback(self, callback: Callable[[Exception], None]) -> None:
        """エラー発生時のコールバックを設定"""
        self._error_callback = callback
    
    def _notify_frame(self, image: ImageData) -> None:
        """フレーム受信を通知"""
        if self._frame_callback:
            self._frame_callback(image)
    
    def _notify_error(self, error: Exception) -> None:
        """エラーを通知"""
        if self._error_callback:
            self._error_callback(error)
    
    # === 抽象メソッド（サブクラスで実装必須） ===
    
    @abstractmethod
    def initialize(self, **kwargs) -> bool:
        """
        プロバイダーを初期化
        
        Returns:
            成功した場合True
        """
        pass
    
    @abstractmethod
    def discover_devices(self) -> List[DeviceInfo]:
        """
        デバイスを検出
        
        Returns:
            検出されたデバイスのリスト
        """
        pass
    
    @abstractmethod
    def connect(self, device_index: int) -> bool:
        """
        指定デバイスに接続
        
        Args:
            device_index: デバイスのインデックス
            
        Returns:
            成功した場合True
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> bool:
        """
        接続を切断
        
        Returns:
            成功した場合True
        """
        pass
    
    @abstractmethod
    def start_acquisition(self) -> bool:
        """
        画像取得を開始
        
        Returns:
            成功した場合True
        """
        pass
    
    @abstractmethod
    def stop_acquisition(self) -> bool:
        """
        画像取得を停止
        
        Returns:
            成功した場合True
        """
        pass
    
    @abstractmethod
    def get_image(self, timeout: float = 1.0) -> Optional[ImageData]:
        """
        画像を1枚取得（同期）
        
        Args:
            timeout: タイムアウト秒数
            
        Returns:
            取得した画像、タイムアウト時はNone
        """
        pass
    
    @abstractmethod
    def set_exposure_time(self, value: float) -> bool:
        """
        露光時間を設定
        
        Args:
            value: 露光時間 (μs)
            
        Returns:
            成功した場合True
        """
        pass
    
    @abstractmethod
    def set_gain(self, value: float) -> bool:
        """
        ゲインを設定
        
        Args:
            value: ゲイン (dB)
            
        Returns:
            成功した場合True
        """
        pass
    
    @abstractmethod
    def cleanup(self) -> None:
        """
        リソースを解放
        """
        pass
    
    # === コンテキストマネージャー対応 ===
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False


def get_provider(mode: str = "auto", **kwargs) -> ICameraProvider:
    """
    カメラプロバイダーを取得するファクトリ関数
    
    Args:
        mode: "harvester", "mock", or "auto"
        **kwargs: プロバイダー固有の引数
        
    Returns:
        ICameraProvider実装インスタンス
    """
    if mode == "mock":
        from mock_camera import MockCameraProvider
        return MockCameraProvider(**kwargs)
    
    elif mode == "harvester":
        from harvester_camera import HarvesterCameraProvider
        return HarvesterCameraProvider(**kwargs)
    
    elif mode == "auto":
        # 自動検出: まずHarvesterを試し、失敗したらモックを使用
        try:
            from harvester_camera import HarvesterCameraProvider
            provider = HarvesterCameraProvider(**kwargs)
            if provider.initialize():
                return provider
        except Exception:
            pass
        
        # Harvesterが使えない場合はモック
        from mock_camera import MockCameraProvider
        return MockCameraProvider(**kwargs)
    
    else:
        raise ValueError(f"Unknown mode: {mode}")
