"""
Harvesterカメラプロバイダー
実際のGigEカメラに接続するための実装
"""
import os
import threading
import time
from typing import List, Optional

import numpy as np

from camera_interface import (
    ICameraProvider, 
    CameraState, 
    DeviceInfo, 
    CameraParameters,
    ImageData
)


class HarvesterCameraProvider(ICameraProvider):
    """
    Harvesterライブラリを使用した実カメラプロバイダー
    
    使用方法:
        provider = HarvesterCameraProvider()
        provider.initialize(cti_file="path/to/producer.cti")
        devices = provider.discover_devices()
        provider.connect(0)
        provider.start_acquisition()
        image = provider.get_image()
        provider.cleanup()
    """
    
    def __init__(self, cti_file: Optional[str] = None):
        """
        Args:
            cti_file: GenTL Producerファイルパス（省略時はプロジェクトフォルダのProducerGEV.cti）
        """
        super().__init__()
        self._cti_file = cti_file
        self._harvester = None
        self._ia = None  # ImageAcquirer
        self._acquisition_thread: Optional[threading.Thread] = None
        self._running = False
        self._frame_id = 0
    
    def initialize(self, **kwargs) -> bool:
        """
        Harvesterを初期化してCTIファイルをロード
        
        Kwargs:
            cti_file: CTIファイルパス（コンストラクタで指定していない場合）
        """
        try:
            from harvesters.core import Harvester
            
            # CTIファイルパスを決定
            cti_file = kwargs.get('cti_file', self._cti_file)
            if cti_file is None:
                # デフォルト: プロジェクトフォルダのProducerGEV.cti
                project_dir = os.path.dirname(os.path.abspath(__file__))
                cti_file = os.path.join(project_dir, "ProducerGEV.cti")
            
            self._cti_file = cti_file
            
            if not os.path.exists(cti_file):
                raise FileNotFoundError(f"CTIファイルが見つかりません: {cti_file}")
            
            # Harvester初期化
            self._harvester = Harvester()
            self._harvester.add_file(cti_file)
            
            print(f"[Harvester] 初期化完了: {os.path.basename(cti_file)}")
            return True
            
        except ImportError:
            print("[Harvester] harvestersライブラリがインストールされていません")
            return False
        except Exception as e:
            print(f"[Harvester] 初期化エラー: {e}")
            self._notify_error(e)
            return False
    
    def discover_devices(self) -> List[DeviceInfo]:
        """デバイスを検出"""
        if self._harvester is None:
            return []
        
        try:
            self._harvester.update()
            
            self._devices = []
            for i, dev_info in enumerate(self._harvester.device_info_list):
                device = DeviceInfo(
                    index=i,
                    vendor=getattr(dev_info, 'vendor', 'Unknown'),
                    model=getattr(dev_info, 'model', 'Unknown'),
                    serial_number=getattr(dev_info, 'serial_number', 'Unknown'),
                    user_defined_name=getattr(dev_info, 'user_defined_name', '')
                )
                self._devices.append(device)
            
            print(f"[Harvester] {len(self._devices)}台のデバイスを検出")
            return self._devices
            
        except Exception as e:
            print(f"[Harvester] デバイス検出エラー: {e}")
            self._notify_error(e)
            return []
    
    def connect(self, device_index: int) -> bool:
        """指定デバイスに接続"""
        if self._harvester is None:
            return False
        
        if device_index < 0 or device_index >= len(self._devices):
            print(f"[Harvester] 無効なデバイスインデックス: {device_index}")
            return False
        
        try:
            # 既存の接続を切断
            if self._ia is not None:
                self.disconnect()
            
            # 新しい接続を作成
            self._ia = self._harvester.create(device_index)
            self._current_device = self._devices[device_index]
            self._state = CameraState.CONNECTED
            
            # カメラパラメータを読み取り
            self._read_camera_parameters()
            
            print(f"[Harvester] 接続完了: {self._current_device}")
            return True
            
        except Exception as e:
            print(f"[Harvester] 接続エラー: {e}")
            self._notify_error(e)
            return False
    
    def disconnect(self) -> bool:
        """接続を切断"""
        try:
            if self._state == CameraState.ACQUIRING:
                self.stop_acquisition()
            
            if self._ia is not None:
                self._ia.destroy()
                self._ia = None
            
            self._current_device = None
            self._state = CameraState.DISCONNECTED
            
            print("[Harvester] 切断完了")
            return True
            
        except Exception as e:
            print(f"[Harvester] 切断エラー: {e}")
            self._notify_error(e)
            return False
    
    def start_acquisition(self) -> bool:
        """画像取得を開始"""
        if self._ia is None:
            return False
        
        try:
            self._ia.start()
            self._state = CameraState.ACQUIRING
            self._frame_id = 0
            
            print("[Harvester] 取得開始")
            return True
            
        except Exception as e:
            print(f"[Harvester] 取得開始エラー: {e}")
            self._notify_error(e)
            return False
    
    def stop_acquisition(self) -> bool:
        """画像取得を停止"""
        if self._ia is None:
            return False
        
        try:
            self._running = False
            
            if self._acquisition_thread is not None:
                self._acquisition_thread.join(timeout=2.0)
                self._acquisition_thread = None
            
            self._ia.stop()
            self._state = CameraState.CONNECTED
            
            print("[Harvester] 取得停止")
            return True
            
        except Exception as e:
            print(f"[Harvester] 取得停止エラー: {e}")
            self._notify_error(e)
            return False
    
    def get_image(self, timeout: float = 1.0) -> Optional[ImageData]:
        """画像を1枚取得"""
        if self._ia is None or self._state != CameraState.ACQUIRING:
            return None
        
        try:
            with self._ia.fetch(timeout=timeout) as buffer:
                component = buffer.payload.components[0]
                
                # 画像データを取得
                width = component.width
                height = component.height
                data = component.data
                
                # 形状を整形
                if len(data.shape) == 1:
                    if hasattr(component, 'num_components_per_pixel'):
                        channels = component.num_components_per_pixel
                        if channels > 1:
                            image_array = data.reshape(height, width, channels)
                        else:
                            image_array = data.reshape(height, width)
                    else:
                        image_array = data.reshape(height, width)
                else:
                    image_array = data
                
                self._frame_id += 1
                
                return ImageData(
                    data=image_array.copy(),
                    width=width,
                    height=height,
                    timestamp=time.time(),
                    frame_id=self._frame_id,
                    pixel_format=self._parameters.pixel_format
                )
                
        except TimeoutError:
            return None
        except Exception as e:
            print(f"[Harvester] 画像取得エラー: {e}")
            self._notify_error(e)
            return None
    
    def set_exposure_time(self, value: float) -> bool:
        """露光時間を設定"""
        if self._ia is None:
            return False
        
        try:
            node_map = self._ia.remote_device.node_map
            node_map.ExposureTime.value = value
            self._parameters.exposure_time = value
            print(f"[Harvester] 露光時間設定: {value} μs")
            return True
            
        except Exception as e:
            print(f"[Harvester] 露光時間設定エラー: {e}")
            self._notify_error(e)
            return False
    
    def set_gain(self, value: float) -> bool:
        """ゲインを設定"""
        if self._ia is None:
            return False
        
        try:
            node_map = self._ia.remote_device.node_map
            node_map.Gain.value = value
            self._parameters.gain = value
            print(f"[Harvester] ゲイン設定: {value} dB")
            return True
            
        except Exception as e:
            print(f"[Harvester] ゲイン設定エラー: {e}")
            self._notify_error(e)
            return False
    
    def cleanup(self) -> None:
        """リソースを解放"""
        try:
            self.disconnect()
            
            if self._harvester is not None:
                self._harvester.reset()
                self._harvester = None
            
            print("[Harvester] クリーンアップ完了")
            
        except Exception as e:
            print(f"[Harvester] クリーンアップエラー: {e}")
    
    def _read_camera_parameters(self) -> None:
        """カメラからパラメータを読み取り"""
        if self._ia is None:
            return
        
        try:
            node_map = self._ia.remote_device.node_map
            
            # 基本パラメータ
            try:
                self._parameters.width = node_map.Width.value
                self._parameters.height = node_map.Height.value
            except:
                pass
            
            try:
                self._parameters.pixel_format = str(node_map.PixelFormat.value)
            except:
                pass
            
            # 露光時間
            try:
                self._parameters.exposure_time = node_map.ExposureTime.value
                self._parameters.exposure_min = node_map.ExposureTime.min
                self._parameters.exposure_max = node_map.ExposureTime.max
            except:
                pass
            
            # ゲイン
            try:
                self._parameters.gain = node_map.Gain.value
                self._parameters.gain_min = node_map.Gain.min
                self._parameters.gain_max = node_map.Gain.max
            except:
                pass
                
        except Exception as e:
            print(f"[Harvester] パラメータ読み取りエラー: {e}")
    
    def get_node_map(self):
        """GenICamノードマップを直接取得（上級者向け）"""
        if self._ia is None:
            return None
        return self._ia.remote_device.node_map
