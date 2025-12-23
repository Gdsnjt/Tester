"""
PLCクライアント
MCプロトコルでPLCに接続するクライアント（外部ライブラリ不使用）
"""
import socket
import struct
import time
from typing import Optional, List, Tuple, Union
from dataclasses import dataclass

from mc_protocol import (
    MCProtocol, MCFrame, MCCommand, PLCSeries,
    DeviceType, get_error_message
)


@dataclass
class ConnectionConfig:
    """接続設定"""
    host: str = "127.0.0.1"
    port: int = 5000
    series: PLCSeries = PLCSeries.Q_SERIES
    timeout: float = 3.0
    network_no: int = 0
    pc_no: int = 0xFF
    dest_module_io: int = 0x03FF
    dest_module_station: int = 0


class PLCClientError(Exception):
    """PLCクライアントエラー"""
    def __init__(self, message: str, error_code: int = 0):
        super().__init__(message)
        self.error_code = error_code


class PLCClient:
    """
    PLCクライアント
    
    MCプロトコルで三菱PLCに接続し、デバイスの読み書きを行う
    外部ライブラリは使用せず、標準のsocketのみ使用
    """
    
    def __init__(self, config: Optional[ConnectionConfig] = None):
        self.config = config or ConnectionConfig()
        self._socket: Optional[socket.socket] = None
        self._serial_no = 0
        self._connected = False
    
    @property
    def is_connected(self) -> bool:
        """接続状態"""
        return self._connected
    
    def connect(self) -> bool:
        """PLCに接続"""
        if self._connected:
            return True
        
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self.config.timeout)
            self._socket.connect((self.config.host, self.config.port))
            self._connected = True
            return True
            
        except Exception as e:
            self._socket = None
            self._connected = False
            raise PLCClientError(f"Connection failed: {e}")
    
    def disconnect(self):
        """PLCから切断"""
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
            self._socket = None
        self._connected = False
    
    def _get_frame(self) -> MCFrame:
        """MCフレームを取得"""
        self._serial_no = (self._serial_no + 1) & 0xFFFF
        return MCFrame(
            series=self.config.series,
            network_no=self.config.network_no,
            pc_no=self.config.pc_no,
            request_dest_module_io=self.config.dest_module_io,
            request_dest_module_station=self.config.dest_module_station,
            serial_no=self._serial_no
        )
    
    def _send_receive(self, request: bytes) -> bytes:
        """リクエスト送信とレスポンス受信"""
        if not self._connected or not self._socket:
            raise PLCClientError("Not connected")
        
        try:
            # 送信
            self._socket.send(request)
            
            # 受信
            response = self._socket.recv(4096)
            
            if not response:
                self._connected = False
                raise PLCClientError("Connection closed by server")
            
            return response
            
        except socket.timeout:
            raise PLCClientError("Communication timeout")
        except Exception as e:
            self._connected = False
            raise PLCClientError(f"Communication error: {e}")
    
    def _check_response(self, response: bytes) -> bytes:
        """レスポンスをチェックしてデータ部を返す"""
        try:
            end_code, data = MCProtocol.parse_response(response, self.config.series)
            
            if end_code != 0:
                error_msg = get_error_message(end_code)
                raise PLCClientError(f"PLC error: {error_msg}", end_code)
            
            return data
            
        except ValueError as e:
            raise PLCClientError(f"Invalid response: {e}")
    
    # === デバイス読み出し ===
    
    def read_bits(self, device: str, start: int, count: int) -> List[bool]:
        """ビットデバイスを読み出し"""
        device_type = DeviceType.from_code(device)
        if device_type is None:
            raise PLCClientError(f"Unknown device: {device}")
        
        frame = self._get_frame()
        request = MCProtocol.build_batch_read_request(
            frame, device_type, start, count, is_bit=True
        )
        
        response = self._send_receive(request)
        data = self._check_response(response)
        
        return [bool(b) for b in data[:count]]
    
    def read_bit(self, device: str, address: int) -> bool:
        """ビットを1点読み出し"""
        result = self.read_bits(device, address, 1)
        return result[0] if result else False
    
    def read_words(self, device: str, start: int, count: int) -> List[int]:
        """ワードデバイスを読み出し"""
        device_type = DeviceType.from_code(device)
        if device_type is None:
            raise PLCClientError(f"Unknown device: {device}")
        
        frame = self._get_frame()
        request = MCProtocol.build_batch_read_request(
            frame, device_type, start, count, is_bit=False
        )
        
        response = self._send_receive(request)
        data = self._check_response(response)
        
        values = []
        for i in range(0, len(data), 2):
            if i + 2 <= len(data):
                values.append(struct.unpack('<H', data[i:i+2])[0])
        
        return values[:count]
    
    def read_word(self, device: str, address: int) -> int:
        """ワードを1点読み出し"""
        result = self.read_words(device, address, 1)
        return result[0] if result else 0
    
    def read_dword(self, device: str, address: int) -> int:
        """ダブルワード（2ワード）を読み出し"""
        values = self.read_words(device, address, 2)
        if len(values) >= 2:
            return (values[1] << 16) | values[0]
        return 0
    
    def read_string(self, device: str, start: int, length: int) -> str:
        """文字列を読み出し"""
        word_count = (length + 1) // 2
        values = self.read_words(device, start, word_count)
        
        chars = []
        for word in values:
            chars.append(chr(word & 0xFF))
            chars.append(chr((word >> 8) & 0xFF))
        
        return ''.join(chars[:length]).rstrip('\x00')
    
    # === デバイス書き込み ===
    
    def write_bits(self, device: str, start: int, values: List[bool]):
        """ビットデバイスに書き込み"""
        device_type = DeviceType.from_code(device)
        if device_type is None:
            raise PLCClientError(f"Unknown device: {device}")
        
        frame = self._get_frame()
        int_values = [1 if v else 0 for v in values]
        request = MCProtocol.build_batch_write_request(
            frame, device_type, start, int_values, is_bit=True
        )
        
        response = self._send_receive(request)
        self._check_response(response)
    
    def write_bit(self, device: str, address: int, value: bool):
        """ビットを1点書き込み"""
        self.write_bits(device, address, [value])
    
    def write_words(self, device: str, start: int, values: List[int]):
        """ワードデバイスに書き込み"""
        device_type = DeviceType.from_code(device)
        if device_type is None:
            raise PLCClientError(f"Unknown device: {device}")
        
        frame = self._get_frame()
        request = MCProtocol.build_batch_write_request(
            frame, device_type, start, values, is_bit=False
        )
        
        response = self._send_receive(request)
        self._check_response(response)
    
    def write_word(self, device: str, address: int, value: int):
        """ワードを1点書き込み"""
        self.write_words(device, address, [value])
    
    def write_dword(self, device: str, address: int, value: int):
        """ダブルワードを書き込み"""
        low = value & 0xFFFF
        high = (value >> 16) & 0xFFFF
        self.write_words(device, address, [low, high])
    
    def write_string(self, device: str, start: int, text: str, length: int):
        """文字列を書き込み"""
        text = text.ljust(length, '\x00')[:length]
        
        words = []
        for i in range(0, len(text), 2):
            low = ord(text[i]) if i < len(text) else 0
            high = ord(text[i + 1]) if i + 1 < len(text) else 0
            words.append((high << 8) | low)
        
        self.write_words(device, start, words)
    
    # === リモート制御 ===
    
    def remote_run(self):
        """リモートRUN"""
        frame = self._get_frame()
        request = MCProtocol.build_remote_control_request(frame, MCCommand.REMOTE_RUN)
        response = self._send_receive(request)
        self._check_response(response)
    
    def remote_stop(self):
        """リモートSTOP"""
        frame = self._get_frame()
        request = MCProtocol.build_remote_control_request(frame, MCCommand.REMOTE_STOP)
        response = self._send_receive(request)
        self._check_response(response)
    
    def remote_pause(self):
        """リモートPAUSE"""
        frame = self._get_frame()
        request = MCProtocol.build_remote_control_request(frame, MCCommand.REMOTE_PAUSE)
        response = self._send_receive(request)
        self._check_response(response)
    
    def remote_reset(self):
        """リモートRESET"""
        frame = self._get_frame()
        request = MCProtocol.build_remote_control_request(frame, MCCommand.REMOTE_RESET)
        response = self._send_receive(request)
        self._check_response(response)
    
    def read_cpu_model(self) -> str:
        """CPU型名を読み出し"""
        frame = self._get_frame()
        request = MCProtocol.build_cpu_model_read_request(frame)
        response = self._send_receive(request)
        data = self._check_response(response)
        
        return data.decode('ascii', errors='ignore').rstrip('\x00')
    
    # === ユーティリティ ===
    
    def test_connection(self) -> bool:
        """接続テスト"""
        try:
            self.read_cpu_model()
            return True
        except:
            return False
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


# === 便利関数 ===

def parse_device(text: str) -> Tuple[str, int]:
    """
    デバイス文字列を解析
    
    例: "D100" -> ("D", 100), "M0" -> ("M", 0)
    """
    text = text.upper().strip()
    
    # 2文字デバイスコード
    for dt in DeviceType:
        if text.startswith(dt.code) and len(dt.code) == 2:
            addr_str = text[2:]
            base = 16 if dt.code in ['ZR'] else 10
            return dt.code, int(addr_str, base)
    
    # 1文字デバイスコード
    for dt in DeviceType:
        if text.startswith(dt.code) and len(dt.code) == 1:
            addr_str = text[1:]
            base = 16 if dt.code in ['X', 'Y', 'B', 'W'] else 10
            return dt.code, int(addr_str, base)
    
    raise ValueError(f"Invalid device: {text}")


def format_device(device: str, address: int) -> str:
    """デバイスをフォーマット"""
    device_type = DeviceType.from_code(device)
    if device_type is None:
        return f"{device}{address}"
    
    if device_type.code in ['X', 'Y', 'B', 'W']:
        return f"{device}{address:X}"
    return f"{device}{address}"
