"""
PLC通信テストクライアント
モックPLCサーバーの動作確認用

様々なMCプロトコルフォーマットをテストする
"""
import socket
import struct
import time
from typing import List, Tuple


class PLCTestClient:
    """PLCテストクライアント"""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 5000):
        self.host = host
        self.port = port
        self.socket = None
    
    def connect(self) -> bool:
        """接続"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)
            self.socket.connect((self.host, self.port))
            print(f"Connected to {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"Connection error: {e}")
            return False
    
    def disconnect(self):
        """切断"""
        if self.socket:
            self.socket.close()
            self.socket = None
            print("Disconnected")
    
    def send_receive(self, data: bytes) -> bytes:
        """送受信"""
        if not self.socket:
            raise RuntimeError("Not connected")
        
        print(f"TX: {data.hex()}")
        self.socket.send(data)
        
        response = self.socket.recv(4096)
        print(f"RX: {response.hex()}")
        return response
    
    # ========================================
    # 3Eフレーム（バイナリ）
    # ========================================
    
    def build_3e_read_request(
        self,
        device_code: int,
        address: int,
        count: int,
        is_bit: bool = False
    ) -> bytes:
        """3Eフレーム読出しリクエスト構築"""
        # サブヘッダ
        frame = struct.pack('<H', 0x5000)
        # ネットワーク番号、PC番号
        frame += struct.pack('<BB', 0, 0xFF)
        # 要求先ユニット
        frame += struct.pack('<HB', 0x03FF, 0)
        
        # データ部
        command = 0x0401  # 一括読出し
        sub_command = 0x0001 if is_bit else 0x0000
        device_data = struct.pack('<I', address)[:3] + bytes([device_code])
        
        data = struct.pack('<HH', command, sub_command)
        data += device_data
        data += struct.pack('<H', count)
        
        # データ長（監視タイマ含む）
        data_length = len(data) + 2
        frame += struct.pack('<H', data_length)
        # 監視タイマ
        frame += struct.pack('<H', 0x0010)
        # データ
        frame += data
        
        return frame
    
    def build_3e_write_request(
        self,
        device_code: int,
        address: int,
        values: List[int],
        is_bit: bool = False
    ) -> bytes:
        """3Eフレーム書込みリクエスト構築"""
        frame = struct.pack('<H', 0x5000)
        frame += struct.pack('<BB', 0, 0xFF)
        frame += struct.pack('<HB', 0x03FF, 0)
        
        command = 0x1401  # 一括書込み
        sub_command = 0x0001 if is_bit else 0x0000
        device_data = struct.pack('<I', address)[:3] + bytes([device_code])
        
        data = struct.pack('<HH', command, sub_command)
        data += device_data
        data += struct.pack('<H', len(values))
        
        if is_bit:
            for v in values:
                data += bytes([0x01 if v else 0x00])
        else:
            for v in values:
                data += struct.pack('<H', v)
        
        data_length = len(data) + 2
        frame += struct.pack('<H', data_length)
        frame += struct.pack('<H', 0x0010)
        frame += data
        
        return frame
    
    def parse_3e_response(self, response: bytes) -> Tuple[int, bytes]:
        """3Eレスポンス解析"""
        if len(response) < 11:
            return -1, b''
        
        end_code = struct.unpack('<H', response[9:11])[0]
        data = response[11:] if len(response) > 11 else b''
        return end_code, data
    
    # ========================================
    # 1Eフレーム（A互換）
    # ========================================
    
    def build_1e_read_request(
        self,
        address: int,
        count: int,
        is_bit: bool = False
    ) -> bytes:
        """1Eフレーム読出しリクエスト（Dレジスタ）"""
        # コマンド（0x00=ビット読出し、0x01=ワード読出し）
        command = 0x00 if is_bit else 0x01
        # PC番号
        pc_no = 0xFF
        # 監視タイマ
        timer = 0x0010
        
        frame = bytes([command, pc_no])
        frame += struct.pack('<H', timer)
        frame += struct.pack('<I', address)
        frame += bytes([count if count <= 255 else 0])  # 0=256点
        
        return frame
    
    def build_1e_write_request(
        self,
        address: int,
        values: List[int],
        is_bit: bool = False
    ) -> bytes:
        """1Eフレーム書込みリクエスト（Dレジスタ）"""
        command = 0x02 if is_bit else 0x03
        pc_no = 0xFF
        timer = 0x0010
        
        count = len(values)
        frame = bytes([command, pc_no])
        frame += struct.pack('<H', timer)
        frame += struct.pack('<I', address)
        frame += bytes([count if count <= 255 else 0])
        
        if is_bit:
            for v in values:
                frame += bytes([0x01 if v else 0x00])
        else:
            for v in values:
                frame += struct.pack('<H', v)
        
        return frame
    
    def parse_1e_response(self, response: bytes) -> Tuple[int, bytes]:
        """1Eレスポンス解析"""
        if len(response) < 2:
            return -1, b''
        
        end_code = response[1]
        data = response[2:] if len(response) > 2 else b''
        return end_code, data
    
    # ========================================
    # 3E ASCII
    # ========================================
    
    def build_3e_ascii_read_request(
        self,
        device_name: str,
        address: int,
        count: int
    ) -> bytes:
        """3E ASCII読出しリクエスト"""
        # 5000 + ネットワーク(2) + PC(2) + ユニット(4) + 局番(2) + 
        # データ長(4) + タイマ(4) + コマンド(4) + サブコマンド(4) + 
        # デバイス名(2) + アドレス(6) + 点数(4)
        
        request = "5000"
        request += "00"  # ネットワーク
        request += "FF"  # PC番号
        request += "03FF"  # ユニット
        request += "00"  # 局番
        
        # データ部
        data_part = "0401"  # 一括読出し
        data_part += "0000"  # サブコマンド（ワード）
        data_part += f"{device_name:>2s}".replace(' ', '*')  # デバイス名
        data_part += f"{address:06X}"  # アドレス
        data_part += f"{count:04X}"  # 点数
        
        data_length = len(data_part) // 2 + 2  # 監視タイマ分
        request += f"{data_length:04X}"
        request += "0010"  # 監視タイマ
        request += data_part
        
        return request.encode('ascii')
    
    def parse_3e_ascii_response(self, response: bytes) -> Tuple[int, str]:
        """3E ASCIIレスポンス解析"""
        try:
            text = response.decode('ascii')
            # D000 + ネット(2) + PC(2) + ユニット(4) + 局番(2) + 長さ(4) + 終了コード(4) + データ
            end_code = int(text[14:18], 16)
            data = text[18:]
            return end_code, data
        except:
            return -1, ""


def test_3e_binary():
    """3Eバイナリフレームテスト"""
    print("\n=== 3E Binary Frame Test ===")
    
    client = PLCTestClient()
    if not client.connect():
        return
    
    try:
        # Dレジスタ書込み
        print("\n--- D0 Write ---")
        request = client.build_3e_write_request(0xA8, 0, [100, 200, 300])
        response = client.send_receive(request)
        end_code, _ = client.parse_3e_response(response)
        print(f"End code: {end_code:#06x} ({'OK' if end_code == 0 else 'ERROR'})")
        
        time.sleep(0.1)
        
        # Dレジスタ読出し
        print("\n--- D0 Read ---")
        request = client.build_3e_read_request(0xA8, 0, 3)
        response = client.send_receive(request)
        end_code, data = client.parse_3e_response(response)
        print(f"End code: {end_code:#06x}")
        if end_code == 0 and len(data) >= 6:
            values = [struct.unpack('<H', data[i:i+2])[0] for i in range(0, len(data), 2)]
            print(f"Values: {values}")
        
        time.sleep(0.1)
        
        # Mリレー書込み
        print("\n--- M0-M2 Write (bit) ---")
        request = client.build_3e_write_request(0x90, 0, [1, 0, 1], is_bit=True)
        response = client.send_receive(request)
        end_code, _ = client.parse_3e_response(response)
        print(f"End code: {end_code:#06x}")
        
        time.sleep(0.1)
        
        # Mリレー読出し
        print("\n--- M0-M2 Read (bit) ---")
        request = client.build_3e_read_request(0x90, 0, 3, is_bit=True)
        response = client.send_receive(request)
        end_code, data = client.parse_3e_response(response)
        print(f"End code: {end_code:#06x}")
        if end_code == 0:
            values = [b for b in data]
            print(f"Bit values: {values}")
        
    finally:
        client.disconnect()


def test_1e_binary():
    """1Eバイナリフレームテスト"""
    print("\n=== 1E Binary Frame Test (A-compatible) ===")
    
    client = PLCTestClient()
    if not client.connect():
        return
    
    try:
        # ワード書込み
        print("\n--- D0 Write (1E) ---")
        request = client.build_1e_write_request(0, [500, 600, 700])
        response = client.send_receive(request)
        end_code, _ = client.parse_1e_response(response)
        print(f"End code: {end_code:#04x}")
        
        time.sleep(0.1)
        
        # ワード読出し
        print("\n--- D0 Read (1E) ---")
        request = client.build_1e_read_request(0, 3)
        response = client.send_receive(request)
        end_code, data = client.parse_1e_response(response)
        print(f"End code: {end_code:#04x}")
        if end_code == 0 and len(data) >= 6:
            values = [struct.unpack('<H', data[i:i+2])[0] for i in range(0, len(data), 2)]
            print(f"Values: {values}")
        
    finally:
        client.disconnect()


def test_3e_ascii():
    """3E ASCIIフレームテスト"""
    print("\n=== 3E ASCII Frame Test ===")
    
    client = PLCTestClient()
    if not client.connect():
        return
    
    try:
        # ASCII読出し
        print("\n--- D0 Read (ASCII) ---")
        request = client.build_3e_ascii_read_request("D*", 0, 3)
        print(f"ASCII request: {request.decode('ascii')}")
        response = client.send_receive(request)
        try:
            print(f"ASCII response: {response.decode('ascii')}")
        except:
            pass
        end_code, data = client.parse_3e_ascii_response(response)
        print(f"End code: {end_code:#06x}, Data: {data}")
        
    finally:
        client.disconnect()


def run_all_tests():
    """全テスト実行"""
    print("=" * 50)
    print("PLC Communication Test")
    print("=" * 50)
    
    test_3e_binary()
    test_1e_binary()
    test_3e_ascii()
    
    print("\n" + "=" * 50)
    print("All tests completed")
    print("=" * 50)


if __name__ == "__main__":
    run_all_tests()
