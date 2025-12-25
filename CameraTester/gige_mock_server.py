"""
GigE Visionモックカメラサーバー
GVCP/GVSPプロトコルを実装した仮想カメラ

任意の画像をGigEカメラ撮影画像として配信可能
"""
import socket
import struct
import threading
import time
import os
import glob
from typing import Optional, List, Dict, Callable, Any
from dataclasses import dataclass, field
import numpy as np
import cv2

from gige_protocol import (
    GVCPCommand, GVCPStatus, GVCPHeader, GVCPAckHeader,
    GVSPHeader, GVSPPacketType, GVSPPayloadType, PixelFormat,
    ImageLeader, ImageTrailer, BootstrapRegister,
    ip_to_int, int_to_ip, mac_to_bytes, pad_string,
    get_local_ip, get_local_mac
)


@dataclass
class MockCameraConfig:
    """モックカメラ設定"""
    # カメラ情報
    vendor: str = "MockCam Corp"
    model: str = "GigE-Mock-1000"
    serial_number: str = "MOCK001"
    user_defined_name: str = "MockCamera"
    device_version: str = "1.0.0"
    
    # ネットワーク設定
    interface_ip: str = ""  # 空の場合は自動検出
    gvcp_port: int = 3956
    gvsp_port: int = 0  # 0の場合は動的割り当て
    
    # 画像設定
    width: int = 640
    height: int = 480
    pixel_format: PixelFormat = PixelFormat.MONO8
    frame_rate: float = 30.0
    
    # パケット設定
    packet_size: int = 1500
    packet_delay: int = 0  # μs


class GigEMockCameraServer:
    """
    GigE Visionモックカメラサーバー
    
    使用方法:
        # 基本的な使用法
        server = GigEMockCameraServer()
        server.start()
        
        # 画像フォルダを指定
        server = GigEMockCameraServer(image_source="path/to/images/")
        server.start()
        
        # 任意の画像を設定
        server.set_image(numpy_array)
        
        # 停止
        server.stop()
    """
    
    def __init__(
        self,
        config: Optional[MockCameraConfig] = None,
        image_source: Optional[str] = None
    ):
        """
        Args:
            config: カメラ設定
            image_source: 画像ソース（フォルダパス、ファイルパターン、動画ファイル）
        """
        self.config = config or MockCameraConfig()
        self._image_source = image_source
        
        # 画像データ
        self._images: List[np.ndarray] = []
        self._current_image_index = 0
        self._current_image: Optional[np.ndarray] = None
        self._video_capture: Optional[cv2.VideoCapture] = None
        
        # ネットワーク
        self._gvcp_socket: Optional[socket.socket] = None
        self._gvsp_socket: Optional[socket.socket] = None
        self._local_ip = ""
        self._local_mac = ""
        
        # ストリーミング
        self._client_ip: Optional[str] = None
        self._client_port: int = 0
        self._streaming = False
        self._stream_thread: Optional[threading.Thread] = None
        self._block_id = 0
        
        # レジスタ
        self._registers: Dict[int, int] = {}
        self._string_registers: Dict[int, str] = {}
        
        # 制御
        self._running = False
        self._gvcp_thread: Optional[threading.Thread] = None
        self._control_privilege = 0
        self._heartbeat_timeout = 3000  # ms
        self._last_heartbeat = 0.0
        
        # コールバック
        self.on_client_connected: Optional[Callable[[str, int], None]] = None
        self.on_client_disconnected: Optional[Callable[[], None]] = None
        self.on_acquisition_start: Optional[Callable[[], None]] = None
        self.on_acquisition_stop: Optional[Callable[[], None]] = None
        self.on_log: Optional[Callable[[str], None]] = None
    
    def _log(self, message: str):
        """ログ出力"""
        if self.on_log:
            self.on_log(message)
        else:
            print(f"[GigE-Mock] {message}")
    
    # ========================================
    # 画像管理
    # ========================================
    
    def load_images(self, source: Optional[str] = None) -> int:
        """
        画像を読み込み
        
        Args:
            source: 画像ソース（省略時はコンストラクタで指定したソース）
        
        Returns:
            読み込んだ画像数
        """
        if source is not None:
            self._image_source = source
        
        self._images = []
        
        if not self._image_source:
            self._generate_test_images()
            return len(self._images)
        
        # 動画ファイルの場合
        if self._image_source.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
            self._video_capture = cv2.VideoCapture(self._image_source)
            if self._video_capture.isOpened():
                self._log(f"動画ファイルを開きました: {self._image_source}")
                return -1  # 動画は枚数不明
            else:
                self._log(f"動画を開けません: {self._image_source}")
                self._video_capture = None
        
        # 画像ファイル/パターン
        if '*' in self._image_source or '?' in self._image_source:
            files = sorted(glob.glob(self._image_source))
        elif os.path.isfile(self._image_source):
            files = [self._image_source]
        elif os.path.isdir(self._image_source):
            patterns = ['*.png', '*.jpg', '*.jpeg', '*.bmp', '*.tiff', '*.tif']
            files = []
            for pattern in patterns:
                files.extend(glob.glob(os.path.join(self._image_source, pattern)))
            files = sorted(files, key=lambda x: os.path.basename(x).lower())
        else:
            files = []
        
        for f in files:
            img = cv2.imread(f, cv2.IMREAD_UNCHANGED)
            if img is not None:
                self._images.append(img)
                self._log(f"読込: {os.path.basename(f)} ({img.shape})")
        
        if not self._images:
            self._log("画像が見つからないため、テストパターンを生成します")
            self._generate_test_images()
        
        # 最初の画像でサイズを設定
        if self._images:
            h, w = self._images[0].shape[:2]
            self.config.width = w
            self.config.height = h
            # ピクセルフォーマットを推定
            if len(self._images[0].shape) == 3:
                self.config.pixel_format = PixelFormat.BGR8
            else:
                self.config.pixel_format = PixelFormat.MONO8
        
        return len(self._images)
    
    def set_image(self, image: np.ndarray) -> None:
        """
        カスタム画像を設定
        
        Args:
            image: NumPy配列形式の画像
        """
        self._images = [image.copy()]
        self._current_image_index = 0
        
        h, w = image.shape[:2]
        self.config.width = w
        self.config.height = h
        
        if len(image.shape) == 3:
            self.config.pixel_format = PixelFormat.BGR8
        else:
            self.config.pixel_format = PixelFormat.MONO8
        
        self._log(f"カスタム画像を設定: {w}x{h}")
    
    def add_image(self, image: np.ndarray) -> None:
        """画像を追加"""
        self._images.append(image.copy())
        self._log(f"画像を追加: 合計 {len(self._images)} 枚")
    
    def _generate_test_images(self) -> None:
        """テスト用画像を生成"""
        w, h = self.config.width, self.config.height
        
        if self.config.pixel_format == PixelFormat.BGR8:
            # カラーテストパターン
            # 1. カラーバー
            img1 = np.zeros((h, w, 3), dtype=np.uint8)
            colors = [(255,255,255), (255,255,0), (0,255,255), (0,255,0),
                     (255,0,255), (255,0,0), (0,0,255), (0,0,0)]
            bar_width = w // len(colors)
            for i, color in enumerate(colors):
                img1[:, i*bar_width:(i+1)*bar_width] = color
            self._images.append(img1)
            
            # 2. グラデーション
            img2 = np.zeros((h, w, 3), dtype=np.uint8)
            for y in range(h):
                for x in range(w):
                    img2[y, x] = [int(x * 255 / w), int(y * 255 / h), 128]
            self._images.append(img2)
            
            # 3. テストパターン
            img3 = np.zeros((h, w, 3), dtype=np.uint8)
            cv2.putText(img3, "GigE Mock Camera", (w//2 - 200, h//2 - 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
            cv2.putText(img3, f"{w}x{h} @ {self.config.frame_rate}fps", 
                       (w//2 - 150, h//2 + 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
            cv2.putText(img3, self.config.serial_number, (w//2 - 80, h//2 + 70),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 200, 100), 2)
            self._images.append(img3)
        else:
            # モノクロテストパターン
            # 1. グラデーション
            img1 = np.zeros((h, w), dtype=np.uint8)
            for y in range(h):
                img1[y, :] = int(y * 255 / h)
            self._images.append(img1)
            
            # 2. チェッカーボード
            img2 = np.zeros((h, w), dtype=np.uint8)
            square_size = 40
            for y in range(0, h, square_size):
                for x in range(0, w, square_size):
                    if ((y // square_size) + (x // square_size)) % 2 == 0:
                        img2[y:y+square_size, x:x+square_size] = 255
            self._images.append(img2)
            
            # 3. テストパターン
            img3 = np.ones((h, w), dtype=np.uint8) * 64
            cv2.putText(img3, "GigE Mock Camera", (w//2 - 180, h//2),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.5, 255, 3)
            cv2.putText(img3, f"{w}x{h}", (w//2 - 50, h//2 + 50),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.0, 200, 2)
            self._images.append(img3)
        
        self._log(f"テストパターンを生成: {len(self._images)} 枚")
    
    def _get_next_image(self) -> np.ndarray:
        """次の画像を取得"""
        if self._video_capture is not None:
            ret, frame = self._video_capture.read()
            if not ret:
                self._video_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self._video_capture.read()
            if ret:
                return frame
        
        if self._images:
            img = self._images[self._current_image_index]
            self._current_image_index = (self._current_image_index + 1) % len(self._images)
            return img
        
        # フォールバック
        return np.zeros((self.config.height, self.config.width), dtype=np.uint8)
    
    # ========================================
    # レジスタ管理
    # ========================================
    
    def _init_registers(self) -> None:
        """レジスタを初期化"""
        # バージョン情報
        self._registers[BootstrapRegister.VERSION] = 0x00010002  # v1.2
        self._registers[BootstrapRegister.DEVICE_MODE] = 0x00000000
        
        # MACアドレス
        mac_bytes = mac_to_bytes(self._local_mac)
        self._registers[BootstrapRegister.DEVICE_MAC_HIGH] = \
            (mac_bytes[0] << 8) | mac_bytes[1]
        self._registers[BootstrapRegister.DEVICE_MAC_LOW] = \
            (mac_bytes[2] << 24) | (mac_bytes[3] << 16) | (mac_bytes[4] << 8) | mac_bytes[5]
        
        # IP設定
        self._registers[BootstrapRegister.SUPPORTED_IP_CONFIG] = 0x00000007  # DHCP, LLA, Static
        self._registers[BootstrapRegister.CURRENT_IP_CONFIG] = 0x00000005  # Static
        self._registers[BootstrapRegister.CURRENT_IP] = ip_to_int(self._local_ip)
        self._registers[BootstrapRegister.CURRENT_SUBNET] = ip_to_int("255.255.255.0")
        self._registers[BootstrapRegister.CURRENT_GATEWAY] = ip_to_int("0.0.0.0")
        
        # 文字列レジスタ
        self._string_registers[BootstrapRegister.MANUFACTURER_NAME] = self.config.vendor
        self._string_registers[BootstrapRegister.MODEL_NAME] = self.config.model
        self._string_registers[BootstrapRegister.DEVICE_VERSION] = self.config.device_version
        self._string_registers[BootstrapRegister.SERIAL_NUMBER] = self.config.serial_number
        self._string_registers[BootstrapRegister.USER_DEFINED_NAME] = self.config.user_defined_name
        
        # ストリーミング設定
        self._registers[BootstrapRegister.STREAM_CHANNEL_COUNT] = 1
        self._registers[BootstrapRegister.STREAM_CHANNEL_0_PORT] = 0
        self._registers[BootstrapRegister.STREAM_CHANNEL_0_PACKET_SIZE] = self.config.packet_size
        self._registers[BootstrapRegister.STREAM_CHANNEL_0_PACKET_DELAY] = self.config.packet_delay
        
        # ハートビート
        self._registers[BootstrapRegister.HEARTBEAT_TIMEOUT] = self._heartbeat_timeout
        self._registers[BootstrapRegister.CONTROL_CHANNEL_PRIVILEGE] = 0
    
    def _read_register(self, address: int) -> int:
        """レジスタ読み出し"""
        # 文字列レジスタの場合
        if address in self._string_registers:
            s = self._string_registers[address]
            # 最初の4バイトを返す
            b = pad_string(s, 4)
            return struct.unpack('>I', b)[0]
        
        return self._registers.get(address, 0)
    
    def _write_register(self, address: int, value: int) -> bool:
        """レジスタ書き込み"""
        self._registers[address] = value
        
        # 特殊レジスタの処理
        if address == BootstrapRegister.STREAM_CHANNEL_0_PORT:
            self._client_port = value
            self._log(f"ストリームポート設定: {value}")
        elif address == BootstrapRegister.STREAM_CHANNEL_0_DEST_IP:
            self._client_ip = int_to_ip(value)
            self._log(f"ストリーム宛先IP設定: {self._client_ip}")
        elif address == BootstrapRegister.CONTROL_CHANNEL_PRIVILEGE:
            self._control_privilege = value
            self._log(f"コントロール権限: {value}")
        elif address == BootstrapRegister.ACQUISITION_START:
            if value == 1:
                self._start_streaming()
        elif address == BootstrapRegister.ACQUISITION_STOP:
            if value == 1:
                self._stop_streaming()
        
        return True
    
    # ========================================
    # GVCPハンドリング
    # ========================================
    
    def _handle_gvcp(self) -> None:
        """GVCPリクエストを処理"""
        while self._running:
            try:
                data, addr = self._gvcp_socket.recvfrom(4096)
                self._process_gvcp_packet(data, addr)
            except socket.timeout:
                # ハートビートチェック
                if self._control_privilege > 0:
                    elapsed = (time.time() - self._last_heartbeat) * 1000
                    if elapsed > self._heartbeat_timeout:
                        self._log("ハートビートタイムアウト - 接続解除")
                        self._control_privilege = 0
                        if self.on_client_disconnected:
                            self.on_client_disconnected()
            except Exception as e:
                if self._running:
                    self._log(f"GVCPエラー: {e}")
    
    def _process_gvcp_packet(self, data: bytes, addr: tuple) -> None:
        """GVCPパケットを処理"""
        try:
            self._log(f"GVCPパケット受信: {addr}, {len(data)} bytes")
            self._log(f"データ先頭: {data[:min(16, len(data))].hex()}")
            
            header = GVCPHeader.unpack(data)
            
            if header.key != 0x42:
                self._log(f"無効なGVCPマジックキー: {header.key:#04x}")
                return
            
            # ハートビート更新
            self._last_heartbeat = time.time()
            
            # コマンド処理
            if header.command == GVCPCommand.DISCOVERY_CMD:
                self._handle_discovery(header, addr)
            elif header.command == GVCPCommand.READREG_CMD:
                self._handle_readreg(header, data[8:], addr)
            elif header.command == GVCPCommand.WRITEREG_CMD:
                self._handle_writereg(header, data[8:], addr)
            elif header.command == GVCPCommand.READMEM_CMD:
                self._handle_readmem(header, data[8:], addr)
            else:
                self._log(f"未対応コマンド: {header.command:#06x}")
                self._send_gvcp_ack(addr, header.command + 1, header.req_id,
                                   GVCPStatus.NOT_IMPLEMENTED)
                
        except Exception as e:
            self._log(f"パケット処理エラー: {e}")
    
    def _handle_discovery(self, header: GVCPHeader, addr: tuple) -> None:
        """Discovery応答"""
        self._log(f"Discovery要求: {addr}")
        
        # Discovery ACK構築（256バイト）
        ack_data = bytearray(256)
        
        # スペックバージョン
        struct.pack_into('>H', ack_data, 0, 0x0001)  # Major
        struct.pack_into('>H', ack_data, 2, 0x0002)  # Minor
        
        # デバイスモード
        struct.pack_into('>I', ack_data, 4, 0)
        
        # MACアドレス
        mac_bytes = mac_to_bytes(self._local_mac)
        ack_data[8:10] = b'\x00\x00'  # Reserved
        ack_data[10:12] = mac_bytes[0:2]
        ack_data[12:16] = mac_bytes[2:6]
        
        # IP設定
        struct.pack_into('>I', ack_data, 16, 0x00000007)  # Supported IP
        struct.pack_into('>I', ack_data, 20, 0x00000005)  # Current IP config
        
        # 予約
        struct.pack_into('>I', ack_data, 24, 0)
        struct.pack_into('>I', ack_data, 28, 0)
        struct.pack_into('>I', ack_data, 32, 0)
        
        # IPアドレス
        struct.pack_into('>I', ack_data, 36, ip_to_int(self._local_ip))
        
        # 予約
        struct.pack_into('>I', ack_data, 40, 0)
        struct.pack_into('>I', ack_data, 44, 0)
        struct.pack_into('>I', ack_data, 48, 0)
        
        # サブネットマスク
        struct.pack_into('>I', ack_data, 52, ip_to_int("255.255.255.0"))
        
        # 予約
        struct.pack_into('>I', ack_data, 56, 0)
        struct.pack_into('>I', ack_data, 60, 0)
        struct.pack_into('>I', ack_data, 64, 0)
        
        # ゲートウェイ
        struct.pack_into('>I', ack_data, 68, 0)
        
        # 製造者名（32バイト）
        vendor = pad_string(self.config.vendor, 32)
        ack_data[72:104] = vendor
        
        # モデル名（32バイト）
        model = pad_string(self.config.model, 32)
        ack_data[104:136] = model
        
        # デバイスバージョン（32バイト）
        version = pad_string(self.config.device_version, 32)
        ack_data[136:168] = version
        
        # 製造者情報（48バイト）
        mfg_info = pad_string("Mock Camera for Testing", 48)
        ack_data[168:216] = mfg_info
        
        # シリアル番号（16バイト）
        serial = pad_string(self.config.serial_number, 16)
        ack_data[216:232] = serial
        
        # ユーザー定義名（16バイト）
        user_name = pad_string(self.config.user_defined_name, 16)
        ack_data[232:248] = user_name
        
        # ACKヘッダ
        ack_header = GVCPAckHeader(
            status=GVCPStatus.SUCCESS,
            command=GVCPCommand.DISCOVERY_ACK,
            length=len(ack_data),
            ack_id=header.req_id
        )
        
        response = ack_header.pack() + bytes(ack_data)
        self._gvcp_socket.sendto(response, addr)
        self._log(f"Discovery ACK送信: {len(response)} bytes")
    
    def _handle_readreg(self, header: GVCPHeader, data: bytes, addr: tuple) -> None:
        """レジスタ読み出し"""
        if len(data) < 4:
            self._send_gvcp_ack(addr, GVCPCommand.READREG_ACK, header.req_id,
                               GVCPStatus.INVALID_PARAMETER)
            return
        
        # 複数レジスタを読み出し可能
        response_data = bytearray()
        for i in range(0, len(data), 4):
            reg_addr = struct.unpack('>I', data[i:i+4])[0]
            value = self._read_register(reg_addr)
            response_data.extend(struct.pack('>I', value))
        
        ack_header = GVCPAckHeader(
            status=GVCPStatus.SUCCESS,
            command=GVCPCommand.READREG_ACK,
            length=len(response_data),
            ack_id=header.req_id
        )
        
        response = ack_header.pack() + bytes(response_data)
        self._gvcp_socket.sendto(response, addr)
    
    def _handle_writereg(self, header: GVCPHeader, data: bytes, addr: tuple) -> None:
        """レジスタ書き込み"""
        self._log(f"WriteReg要求: {addr}, len={len(data)}")
        if len(data) < 8:
            self._log(f"WriteReg: 無効なパラメータ長: {len(data)}")
            self._send_gvcp_ack(addr, GVCPCommand.WRITEREG_ACK, header.req_id,
                               GVCPStatus.INVALID_PARAMETER)
            return
        
        # 複数レジスタを書き込み可能
        for i in range(0, len(data), 8):
            reg_addr = struct.unpack('>I', data[i:i+4])[0]
            value = struct.unpack('>I', data[i+4:i+8])[0]
            self._log(f"WriteReg: addr={reg_addr:#010x}, value={value:#010x}")
            self._write_register(reg_addr, value)
        
        # インデックスを返す
        response_data = struct.pack('>I', len(data) // 8)
        
        ack_header = GVCPAckHeader(
            status=GVCPStatus.SUCCESS,
            command=GVCPCommand.WRITEREG_ACK,
            length=len(response_data),
            ack_id=header.req_id
        )
        
        response = ack_header.pack() + bytes(response_data)
        self._gvcp_socket.sendto(response, addr)
    
    def _handle_readmem(self, header: GVCPHeader, data: bytes, addr: tuple) -> None:
        """メモリ読み出し（文字列レジスタ用）"""
        if len(data) < 8:
            self._send_gvcp_ack(addr, GVCPCommand.READMEM_ACK, header.req_id,
                               GVCPStatus.INVALID_PARAMETER)
            return
        
        mem_addr = struct.unpack('>I', data[0:4])[0]
        count = struct.unpack('>I', data[4:8])[0]
        
        # 文字列レジスタを探す
        response_data = bytearray(count)
        
        if mem_addr in self._string_registers:
            s = self._string_registers[mem_addr]
            s_bytes = pad_string(s, count)
            response_data = bytearray(s_bytes)
        
        # アドレスを先頭に追加
        response_data = struct.pack('>I', mem_addr) + bytes(response_data)
        
        ack_header = GVCPAckHeader(
            status=GVCPStatus.SUCCESS,
            command=GVCPCommand.READMEM_ACK,
            length=len(response_data),
            ack_id=header.req_id
        )
        
        response = ack_header.pack() + bytes(response_data)
        self._gvcp_socket.sendto(response, addr)
    
    def _send_gvcp_ack(self, addr: tuple, command: int, ack_id: int, 
                       status: int = GVCPStatus.SUCCESS, data: bytes = b'') -> None:
        """GVCP ACK送信"""
        ack_header = GVCPAckHeader(
            status=status,
            command=command,
            length=len(data),
            ack_id=ack_id
        )
        response = ack_header.pack() + data
        self._gvcp_socket.sendto(response, addr)
    
    # ========================================
    # GVSPストリーミング
    # ========================================
    
    def _start_streaming(self) -> None:
        """ストリーミング開始"""
        if self._streaming:
            return
        
        if not self._client_ip or self._client_port == 0:
            self._log("ストリーミング宛先が未設定")
            return
        
        self._streaming = True
        self._block_id = 0
        self._stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._stream_thread.start()
        
        self._log(f"ストリーミング開始: {self._client_ip}:{self._client_port}")
        
        if self.on_acquisition_start:
            self.on_acquisition_start()
    
    def _stop_streaming(self) -> None:
        """ストリーミング停止"""
        if not self._streaming:
            return
        
        self._streaming = False
        
        if self._stream_thread:
            self._stream_thread.join(timeout=2.0)
            self._stream_thread = None
        
        self._log("ストリーミング停止")
        
        if self.on_acquisition_stop:
            self.on_acquisition_stop()
    
    def _stream_loop(self) -> None:
        """ストリーミングループ"""
        frame_interval = 1.0 / self.config.frame_rate
        last_frame_time = time.time()
        
        while self._streaming:
            try:
                # フレームレート制御
                elapsed = time.time() - last_frame_time
                if elapsed < frame_interval:
                    time.sleep(frame_interval - elapsed)
                last_frame_time = time.time()
                
                # 画像取得
                image = self._get_next_image()
                
                # ストリーミング送信
                self._send_image(image)
                
                self._block_id += 1
                
            except Exception as e:
                if self._streaming:
                    self._log(f"ストリーミングエラー: {e}")
    
    def _send_image(self, image: np.ndarray) -> None:
        """画像を送信"""
        if self._gvsp_socket is None:
            return
        
        try:
            dest = (self._client_ip, self._client_port)
            timestamp = int(time.time() * 1e9)  # ナノ秒
            
            # 画像データを準備
            if len(image.shape) == 3:
                pixel_format = PixelFormat.BGR8
                image_data = image.tobytes()
            else:
                pixel_format = PixelFormat.MONO8
                image_data = image.tobytes()
            
            height, width = image.shape[:2]
            
            self._log(f"画像送信開始: {width}x{height}, {len(image_data)} bytes")
            
            # 1. Data Leader送信
            leader = ImageLeader(
                payload_type=GVSPPayloadType.IMAGE,
                timestamp=timestamp,
                pixel_format=pixel_format,
                width=width,
                height=height
            )
            
            gvsp_header = GVSPHeader(
                status=GVCPStatus.SUCCESS,
                block_id=self._block_id & 0xFFFF,
                packet_format=GVSPPacketType.DATA_LEADER,
                packet_id=0
            )
            
            leader_packet = gvsp_header.pack() + leader.pack()
            self._gvsp_socket.sendto(leader_packet, dest)
            
            # 2. Data Payload送信
            payload_size = self.config.packet_size - 8  # ヘッダ分を引く
            packet_id = 1
            offset = 0
            
            while offset < len(image_data):
                chunk = image_data[offset:offset + payload_size]
                
                gvsp_header = GVSPHeader(
                    status=GVCPStatus.SUCCESS,
                    block_id=self._block_id & 0xFFFF,
                    packet_format=GVSPPacketType.DATA_PAYLOAD,
                    packet_id=packet_id
                )
                
                payload_packet = gvsp_header.pack() + chunk
                self._gvsp_socket.sendto(payload_packet, dest)
                
                offset += payload_size
                packet_id += 1
                
                # パケット遅延
                if self.config.packet_delay > 0:
                    time.sleep(self.config.packet_delay / 1e6)
            
            self._log(f"画像送信完了: {packet_id} パケット")
            
            # 3. Data Trailer送信
            trailer = ImageTrailer(
                payload_type=GVSPPayloadType.IMAGE,
                size_y=height
            )
            
            gvsp_header = GVSPHeader(
                status=GVCPStatus.SUCCESS,
                block_id=self._block_id & 0xFFFF,
                packet_format=GVSPPacketType.DATA_TRAILER,
                packet_id=packet_id
            )
            
            trailer_packet = gvsp_header.pack() + trailer.pack()
            self._gvsp_socket.sendto(trailer_packet, dest)
            self._log(f"Trailer送信: packet_id={packet_id}")
            
        except Exception as e:
            self._log(f"画像送信エラー: {e}")
    
    # ========================================
    # サーバー制御
    # ========================================
    
    def start(self) -> bool:
        """サーバーを開始"""
        if self._running:
            return False
        
        try:
            # ローカルIPとMACを取得
            if self.config.interface_ip:
                self._local_ip = self.config.interface_ip
            else:
                self._local_ip = get_local_ip()
            self._local_mac = get_local_mac()
            
            # レジスタ初期化
            self._init_registers()
            
            # 画像読み込み
            self.load_images()
            
            # GVCPソケット作成
            self._gvcp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._gvcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._gvcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._gvcp_socket.bind(('', self.config.gvcp_port))
            self._gvcp_socket.settimeout(1.0)
            
            # GVSPソケット作成
            self._gvsp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            if self.config.gvsp_port > 0:
                self._gvsp_socket.bind(('', self.config.gvsp_port))
            
            self._running = True
            self._gvcp_thread = threading.Thread(target=self._handle_gvcp, daemon=True)
            self._gvcp_thread.start()
            
            self._log(f"サーバー開始: {self._local_ip}:{self.config.gvcp_port}")
            self._log(f"カメラ: {self.config.model} (SN: {self.config.serial_number})")
            return True
            
        except Exception as e:
            self._log(f"サーバー開始エラー: {e}")
            return False
    
    def stop(self) -> None:
        """サーバーを停止"""
        self._running = False
        self._stop_streaming()
        
        if self._gvcp_socket:
            self._gvcp_socket.close()
            self._gvcp_socket = None
        
        if self._gvsp_socket:
            self._gvsp_socket.close()
            self._gvsp_socket = None
        
        if self._gvcp_thread:
            self._gvcp_thread.join(timeout=2.0)
            self._gvcp_thread = None
        
        if self._video_capture:
            self._video_capture.release()
            self._video_capture = None
        
        self._log("サーバー停止")
    
    @property
    def is_running(self) -> bool:
        """サーバーが実行中か"""
        return self._running
    
    @property
    def is_streaming(self) -> bool:
        """ストリーミング中か"""
        return self._streaming
    
    @property
    def local_ip(self) -> str:
        """ローカルIPアドレス"""
        return self._local_ip


# ========================================
# テスト用メイン
# ========================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="GigE Vision Mock Camera Server")
    parser.add_argument("--images", "-i", help="Image source folder or pattern")
    parser.add_argument("--width", "-W", type=int, default=640, help="Image width")
    parser.add_argument("--height", "-H", type=int, default=480, help="Image height")
    parser.add_argument("--fps", "-f", type=float, default=30.0, help="Frame rate")
    parser.add_argument("--color", "-c", action="store_true", help="Color mode")
    parser.add_argument("--serial", "-s", default="MOCK001", help="Serial number")
    args = parser.parse_args()
    
    config = MockCameraConfig(
        width=args.width,
        height=args.height,
        frame_rate=args.fps,
        serial_number=args.serial,
        pixel_format=PixelFormat.BGR8 if args.color else PixelFormat.MONO8
    )
    
    server = GigEMockCameraServer(config=config, image_source=args.images)
    
    try:
        if server.start():
            print("\nPress Ctrl+C to stop...")
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
