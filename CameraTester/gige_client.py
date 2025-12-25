"""
GigE Visionクライアント
GVCP/GVSPプロトコルでカメラに直接接続

モックカメラサーバーおよび実GigEカメラに対応
"""
import socket
import struct
import threading
import time
from typing import Optional, List, Callable, Tuple
from dataclasses import dataclass
import numpy as np

from gige_protocol import (
    GVCPCommand, GVCPStatus, GVCPHeader, GVCPAckHeader,
    GVSPHeader, GVSPPacketType, GVSPPayloadType, PixelFormat,
    BootstrapRegister,
    ip_to_int, int_to_ip
)

from camera_interface import (
    ICameraProvider,
    CameraState,
    DeviceInfo,
    CameraParameters,
    ImageData
)


@dataclass
class GigEDeviceInfo:
    """GigEカメラデバイス情報"""
    ip_address: str
    mac_address: str
    vendor: str
    model: str
    serial_number: str
    user_defined_name: str
    version: str = ""
    
    @property
    def ip(self) -> str:
        """IPアドレス（エイリアス）"""
        return self.ip_address
    
    def __str__(self) -> str:
        name = self.user_defined_name or self.model
        return f"{self.vendor} {name} ({self.ip_address})"


class GigEVisionClient(ICameraProvider):
    """
    GigE Visionクライアント
    
    GVCPプロトコルでカメラを検出・制御し、
    GVSPプロトコルで画像を受信
    
    使用方法:
        client = GigEVisionClient()
        client.initialize()
        
        # デバイス検出
        devices = client.discover_devices()
        
        # 接続
        client.connect(0)
        
        # 取得開始
        client.start_acquisition()
        
        # 画像取得
        image = client.get_image()
        
        # 停止
        client.stop_acquisition()
        client.disconnect()
    """
    
    def __init__(self, receive_port: int = 0):
        """
        Args:
            receive_port: 画像受信ポート（0=自動割り当て）
        """
        super().__init__()
        
        self._receive_port = receive_port
        self._gvcp_socket: Optional[socket.socket] = None
        self._gvsp_socket: Optional[socket.socket] = None
        self._gvcp_port = 3956  # デフォルトのGVCPポート
        
        self._gige_devices: List[GigEDeviceInfo] = []
        self._current_gige_device: Optional[GigEDeviceInfo] = None
        
        # GVCP
        self._req_id = 1
        self._timeout = 1.0
        
        # GVSP
        self._receiving = False
        self._receive_thread: Optional[threading.Thread] = None
        self._image_buffer: Optional[np.ndarray] = None
        self._image_ready = threading.Event()
        self._current_block_id = 0
        self._frame_id = 0
        
        # 画像メタデータ
        self._image_width = 0
        self._image_height = 0
        self._pixel_format = PixelFormat.MONO8
        self._timestamp = 0
        
        # パケットバッファ
        self._packet_buffer: dict = {}
    
    def initialize(self, **kwargs) -> bool:
        """クライアントを初期化"""
        try:
            # GVCPソケット作成
            self._gvcp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._gvcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._gvcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._gvcp_socket.bind(('', 0))
            self._gvcp_socket.settimeout(self._timeout)
            
            # GVSPソケット作成
            self._gvsp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._gvsp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
            self._gvsp_socket.bind(('', self._receive_port))
            self._gvsp_socket.settimeout(0.5)
            
            # 実際のポートを取得
            self._receive_port = self._gvsp_socket.getsockname()[1]
            
            print(f"[GigE Client] 初期化完了 (受信ポート: {self._receive_port})")
            return True
            
        except Exception as e:
            print(f"[GigE Client] 初期化エラー: {e}")
            self._notify_error(e)
            return False
    
    def cleanup(self) -> None:
        """リソースを解放"""
        self.stop_acquisition()
        self.disconnect()
        
        if self._gvcp_socket:
            self._gvcp_socket.close()
            self._gvcp_socket = None
        
        if self._gvsp_socket:
            self._gvsp_socket.close()
            self._gvsp_socket = None
    
    # ========================================
    # デバイス検出
    # ========================================
    
    def discover_devices(self, timeout: float = 1.0) -> List[DeviceInfo]:
        """
        ネットワーク上のGigEカメラを検出
        
        Args:
            timeout: 検出タイムアウト（秒）
        
        Returns:
            検出されたデバイスリスト
        """
        self._devices = []
        self._gige_devices = []
        
        if self._gvcp_socket is None:
            return []
        
        try:
            # Discoveryコマンド送信
            header = GVCPHeader(
                key=0x42,
                flag=0x11,  # Broadcast acknowledge
                command=GVCPCommand.DISCOVERY_CMD,
                length=0,
                req_id=self._get_req_id()
            )
            
            # ブロードキャスト送信
            self._gvcp_socket.sendto(header.pack(), ('<broadcast>', 3956))
            
            # 応答を収集
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    data, addr = self._gvcp_socket.recvfrom(4096)
                    device = self._parse_discovery_ack(data, addr[0])
                    if device:
                        self._gige_devices.append(device)
                except socket.timeout:
                    break
            
            # ICameraProvider形式に変換
            for i, gige_dev in enumerate(self._gige_devices):
                device = DeviceInfo(
                    index=i,
                    vendor=gige_dev.vendor,
                    model=gige_dev.model,
                    serial_number=gige_dev.serial_number,
                    user_defined_name=gige_dev.user_defined_name
                )
                self._devices.append(device)
            
            print(f"[GigE Client] {len(self._devices)}台のカメラを検出")
            return self._devices
            
        except Exception as e:
            print(f"[GigE Client] 検出エラー: {e}")
            return []
    
    def _parse_discovery_ack(self, data: bytes, ip: str) -> Optional[GigEDeviceInfo]:
        """Discovery ACKを解析"""
        try:
            if len(data) < 256:
                return None
            
            # ACKヘッダ
            ack = GVCPAckHeader.unpack(data[:8])
            if ack.command != GVCPCommand.DISCOVERY_ACK:
                return None
            
            # ペイロード解析
            payload = data[8:]
            
            # MACアドレス
            mac_high = struct.unpack('>H', payload[8:10])[0]
            mac_low = struct.unpack('>I', payload[10:14])[0]
            mac = f"{(mac_high >> 8) & 0xFF:02X}:{mac_high & 0xFF:02X}:" \
                  f"{(mac_low >> 24) & 0xFF:02X}:{(mac_low >> 16) & 0xFF:02X}:" \
                  f"{(mac_low >> 8) & 0xFF:02X}:{mac_low & 0xFF:02X}"
            
            # 製造者名
            vendor = payload[64:96].rstrip(b'\x00').decode('utf-8', errors='ignore')
            
            # モデル名
            model = payload[96:128].rstrip(b'\x00').decode('utf-8', errors='ignore')
            
            # デバイスバージョン
            version = payload[128:160].rstrip(b'\x00').decode('utf-8', errors='ignore')
            
            # シリアル番号
            serial = payload[208:224].rstrip(b'\x00').decode('utf-8', errors='ignore')
            
            # ユーザー定義名
            user_name = payload[224:240].rstrip(b'\x00').decode('utf-8', errors='ignore')
            
            return GigEDeviceInfo(
                ip_address=ip,
                mac_address=mac,
                vendor=vendor,
                model=model,
                serial_number=serial,
                user_defined_name=user_name,
                version=version
            )
            
        except Exception as e:
            print(f"[GigE Client] Discovery ACK解析エラー: {e}")
            return None
    
    # ========================================
    # 接続制御
    # ========================================
    
    def connect(self, target, port: int = 3956) -> bool:
        """
        デバイスに接続
        
        Args:
            target: デバイスインデックス（int）またはIPアドレス（str）
            port: GVCPポート（デフォルト: 3956）
        """
        self._gvcp_port = port
        try:
            if isinstance(target, str):
                # IPアドレスで接続
                self._current_gige_device = GigEDeviceInfo(
                    ip_address=target,
                    mac_address="",
                    vendor="Unknown",
                    model="Unknown",
                    serial_number="",
                    user_defined_name=""
                )
                self._current_device = DeviceInfo(
                    index=0,
                    vendor="Unknown",
                    model="Unknown",
                    serial_number="",
                    user_defined_name=""
                )
            elif isinstance(target, int):
                # インデックスで接続
                if target < 0 or target >= len(self._gige_devices):
                    print(f"[GigE Client] 無効なデバイスインデックス: {target}")
                    return False
                self._current_gige_device = self._gige_devices[target]
                self._current_device = self._devices[target]
            else:
                print(f"[GigE Client] 無効なターゲット: {target}")
                return False
            
            # コントロール権限を取得
            if not self._write_register(BootstrapRegister.CONTROL_CHANNEL_PRIVILEGE, 2):
                print("[GigE Client] コントロール権限の取得に失敗")
                return False
            
            # カメラパラメータを読み取り
            self._read_camera_parameters()
            
            self._state = CameraState.CONNECTED
            print(f"[GigE Client] 接続完了: {self._current_gige_device}")
            return True
            
        except Exception as e:
            print(f"[GigE Client] 接続エラー: {e}")
            self._notify_error(e)
            return False
    
    def disconnect(self) -> bool:
        """接続を切断"""
        try:
            if self._state == CameraState.ACQUIRING:
                self.stop_acquisition()
            
            if self._current_gige_device:
                # コントロール権限を解放
                self._write_register(BootstrapRegister.CONTROL_CHANNEL_PRIVILEGE, 0)
            
            self._current_gige_device = None
            self._current_device = None
            self._state = CameraState.DISCONNECTED
            
            print("[GigE Client] 切断完了")
            return True
            
        except Exception as e:
            print(f"[GigE Client] 切断エラー: {e}")
            return False
    
    def _read_camera_parameters(self) -> None:
        """カメラパラメータを読み取り"""
        # TODO: 実際のカメラからパラメータを読み取る
        # 現時点ではデフォルト値を使用
        pass
    
    def set_exposure_time(self, value: float) -> bool:
        """
        露光時間を設定
        
        Args:
            value: 露光時間 (μs)
            
        Returns:
            成功した場合True
        """
        # GigE Visionの標準では露光時間はGenICamノードで設定
        # 簡易実装としてパラメータを保持
        self._parameters.exposure_time = value
        return True
    
    def set_gain(self, value: float) -> bool:
        """
        ゲインを設定
        
        Args:
            value: ゲイン (dB)
            
        Returns:
            成功した場合True
        """
        # GigE Visionの標準ではゲインはGenICamノードで設定
        # 簡易実装としてパラメータを保持
        self._parameters.gain = value
        return True
    
    # ========================================
    # 取得制御
    # ========================================
    
    def start_acquisition(self) -> bool:
        """画像取得を開始"""
        if self._state != CameraState.CONNECTED:
            return False
        
        if self._current_gige_device is None:
            return False
        
        try:
            # ストリームチャネルを設定
            local_ip = self._get_local_ip()
            self._write_register(
                BootstrapRegister.STREAM_CHANNEL_0_DEST_IP,
                ip_to_int(local_ip)
            )
            self._write_register(
                BootstrapRegister.STREAM_CHANNEL_0_PORT,
                self._receive_port
            )
            
            # 受信スレッド開始
            self._receiving = True
            self._receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self._receive_thread.start()
            
            # 取得開始コマンド
            self._write_register(BootstrapRegister.ACQUISITION_START, 1)
            
            self._state = CameraState.ACQUIRING
            self._frame_id = 0
            
            print("[GigE Client] 取得開始")
            return True
            
        except Exception as e:
            print(f"[GigE Client] 取得開始エラー: {e}")
            self._notify_error(e)
            return False
    
    def stop_acquisition(self) -> bool:
        """画像取得を停止"""
        try:
            if self._current_gige_device:
                # 取得停止コマンド
                self._write_register(BootstrapRegister.ACQUISITION_STOP, 1)
            
            self._receiving = False
            
            if self._receive_thread:
                self._receive_thread.join(timeout=2.0)
                self._receive_thread = None
            
            if self._state == CameraState.ACQUIRING:
                self._state = CameraState.CONNECTED
            
            print("[GigE Client] 取得停止")
            return True
            
        except Exception as e:
            print(f"[GigE Client] 取得停止エラー: {e}")
            return False
    
    def get_image(self, timeout: float = 1.0) -> Optional[ImageData]:
        """画像を1枚取得"""
        if self._state != CameraState.ACQUIRING:
            return None
        
        # 画像待機
        if self._image_ready.wait(timeout=timeout):
            self._image_ready.clear()
            
            if self._image_buffer is not None:
                image_data = ImageData(
                    data=self._image_buffer.copy(),
                    width=self._image_width,
                    height=self._image_height,
                    timestamp=self._timestamp / 1e9,
                    frame_id=self._frame_id,
                    pixel_format=self._get_pixel_format_name()
                )
                self._frame_id += 1
                return image_data
        
        return None
    
    def capture(self, timeout: float = 1.0) -> Optional[np.ndarray]:
        """
        簡易画像取得メソッド
        
        Args:
            timeout: タイムアウト（秒）
        
        Returns:
            NumPy配列形式の画像（取得失敗時はNone）
        """
        image_data = self.get_image(timeout=timeout)
        if image_data is not None:
            return image_data.data
        return None
    
    def _get_pixel_format_name(self) -> str:
        """ピクセルフォーマット名を取得"""
        format_names = {
            PixelFormat.MONO8: "Mono8",
            PixelFormat.MONO16: "Mono16",
            PixelFormat.BGR8: "BGR8",
            PixelFormat.RGB8: "RGB8",
        }
        return format_names.get(self._pixel_format, "Unknown")
    
    # ========================================
    # GVSP受信
    # ========================================
    
    def _receive_loop(self) -> None:
        """GVSP受信ループ"""
        while self._receiving:
            try:
                data, addr = self._gvsp_socket.recvfrom(65536)
                self._process_gvsp_packet(data)
            except socket.timeout:
                continue
            except Exception as e:
                if self._receiving:
                    print(f"[GigE Client] 受信エラー: {e}")
    
    def _process_gvsp_packet(self, data: bytes) -> None:
        """GVSPパケットを処理"""
        try:
            if len(data) < 8:
                return
            
            header = GVSPHeader.unpack(data[:8])
            payload = data[8:]
            
            block_id = header.block_id
            packet_type = header.packet_format
            packet_id = header.packet_id
            
            if packet_type == GVSPPacketType.DATA_LEADER:
                self._handle_leader(block_id, payload)
            elif packet_type == GVSPPacketType.DATA_PAYLOAD:
                self._handle_payload(block_id, packet_id, payload)
            elif packet_type == GVSPPacketType.DATA_TRAILER:
                self._handle_trailer(block_id, payload)
                
        except Exception as e:
            print(f"[GigE Client] パケット処理エラー: {e}")
    
    def _handle_leader(self, block_id: int, payload: bytes) -> None:
        """Leaderパケット処理"""
        # ImageLeaderは34バイト（最低22バイト必要）
        if len(payload) < 22:
            return
        
        try:
            # 画像メタデータ解析
            payload_type = struct.unpack('>H', payload[0:2])[0]
            self._timestamp = struct.unpack('>Q', payload[2:10])[0]
            self._pixel_format = struct.unpack('>I', payload[10:14])[0]
            self._image_width = struct.unpack('>I', payload[14:18])[0]
            self._image_height = struct.unpack('>I', payload[18:22])[0]
            
            # 画像バッファを準備
            if self._pixel_format in [PixelFormat.BGR8, PixelFormat.RGB8]:
                self._image_buffer = np.zeros(
                    (self._image_height, self._image_width, 3), 
                    dtype=np.uint8
                )
            else:
                self._image_buffer = np.zeros(
                    (self._image_height, self._image_width), 
                    dtype=np.uint8
                )
            
            # パケットバッファをクリア
            self._packet_buffer = {}
            self._current_block_id = block_id
        except Exception:
            pass
    
    def _handle_payload(self, block_id: int, packet_id: int, payload: bytes) -> None:
        """Payloadパケット処理"""
        if block_id != self._current_block_id:
            return
        
        self._packet_buffer[packet_id] = payload
    
    def _handle_trailer(self, block_id: int, payload: bytes) -> None:
        """Trailerパケット処理"""
        if block_id != self._current_block_id:
            return
        
        if self._image_buffer is None:
            return
        
        try:
            # パケットを順番に結合
            sorted_ids = sorted(self._packet_buffer.keys())
            image_data = b''
            for pid in sorted_ids:
                image_data += self._packet_buffer[pid]
            
            # 画像データをバッファにコピー
            expected_size = self._image_buffer.nbytes
            if len(image_data) >= expected_size:
                flat = np.frombuffer(image_data[:expected_size], dtype=np.uint8)
                self._image_buffer = flat.reshape(self._image_buffer.shape)
                
                # 画像準備完了を通知
                self._image_ready.set()
            
        except Exception as e:
            print(f"[GigE Client] 画像構築エラー: {e}")
        
        # バッファクリア
        self._packet_buffer = {}
    
    # ========================================
    # GVCPコマンド
    # ========================================
    
    def _get_req_id(self) -> int:
        """リクエストIDを取得"""
        req_id = self._req_id
        self._req_id = (self._req_id + 1) & 0xFFFF
        return req_id
    
    def _send_gvcp_command(self, command: int, data: bytes = b'') -> Tuple[int, bytes]:
        """GVCPコマンドを送信してACKを受信"""
        if self._gvcp_socket is None or self._current_gige_device is None:
            return GVCPStatus.ERROR, b''
        
        header = GVCPHeader(
            key=0x42,
            flag=0x01,
            command=command,
            length=len(data),
            req_id=self._get_req_id()
        )
        
        packet = header.pack() + data
        dest = (self._current_gige_device.ip_address, self._gvcp_port)
        
        try:
            self._gvcp_socket.sendto(packet, dest)
            
            response, from_addr = self._gvcp_socket.recvfrom(4096)
            ack = GVCPAckHeader.unpack(response[:8])
            
            return ack.status, response[8:]
            
        except socket.timeout:
            return GVCPStatus.NO_MSG, b''
        except Exception as e:
            print(f"[GigE Client] GVCPエラー: {e}")
            return GVCPStatus.ERROR, b''
    
    def _read_register(self, address: int) -> Optional[int]:
        """レジスタ読み出し"""
        data = struct.pack('>I', address)
        status, response = self._send_gvcp_command(GVCPCommand.READREG_CMD, data)
        
        if status == GVCPStatus.SUCCESS and len(response) >= 4:
            return struct.unpack('>I', response[:4])[0]
        return None
    
    def _write_register(self, address: int, value: int) -> bool:
        """レジスタ書き込み"""
        data = struct.pack('>II', address, value)
        print(f"[GigE Client] WriteReg: addr={address:#010x}, value={value:#010x}")
        status, response = self._send_gvcp_command(GVCPCommand.WRITEREG_CMD, data)
        print(f"[GigE Client] WriteReg結果: status={status}")
        return status == GVCPStatus.SUCCESS
    
    def _get_local_ip(self) -> str:
        """ローカルIPアドレスを取得"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((self._current_gige_device.ip_address, 3956))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"


# ========================================
# テスト用メイン
# ========================================

if __name__ == "__main__":
    client = GigEVisionClient()
    
    if client.initialize():
        print("\n検出中...")
        devices = client.discover_devices(timeout=2.0)
        
        if devices:
            print(f"\n検出されたカメラ:")
            for i, dev in enumerate(devices):
                print(f"  [{i}] {dev}")
            
            print("\n最初のカメラに接続...")
            if client.connect(0):
                print("取得開始...")
                if client.start_acquisition():
                    print("画像取得中... (Ctrl+C で停止)")
                    
                    try:
                        for i in range(10):
                            image = client.get_image(timeout=2.0)
                            if image:
                                print(f"Frame {image.frame_id}: {image.width}x{image.height}")
                            else:
                                print("タイムアウト")
                    except KeyboardInterrupt:
                        pass
                    
                    client.stop_acquisition()
                client.disconnect()
        else:
            print("カメラが見つかりませんでした")
        
        client.cleanup()
