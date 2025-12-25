"""
MC Protocol 実装
三菱PLC通信用のMCプロトコル（3Eフレーム/4Eフレーム）

対応シリーズ:
- Qシリーズ: 3Eフレーム
- iQ-Rシリーズ: 4Eフレーム
"""
import struct
from enum import Enum
from dataclasses import dataclass
from typing import List, Tuple, Optional, Union


class PLCSeries(Enum):
    """PLCシリーズ"""
    Q_SERIES = "Q"       # Qシリーズ（3Eフレーム）
    IQR_SERIES = "iQ-R"  # iQ-Rシリーズ（4Eフレーム）


class DeviceType(Enum):
    """デバイスタイプ"""
    # ビットデバイス
    M = ("M", 0x90, 1, "内部リレー")
    L = ("L", 0x92, 1, "ラッチリレー")
    F = ("F", 0x93, 1, "アナンシエータ")
    V = ("V", 0x94, 1, "エッジリレー")
    B = ("B", 0xA0, 1, "リンクリレー")
    X = ("X", 0x9C, 1, "入力")
    Y = ("Y", 0x9D, 1, "出力")
    S = ("S", 0x98, 1, "ステップリレー")
    SS = ("SS", 0x98, 1, "ステップリレー")
    SC = ("SC", 0xC6, 1, "積算タイマ接点")
    TC = ("TC", 0xC0, 1, "タイマ接点")
    TS = ("TS", 0xC1, 1, "タイマコイル")
    CC = ("CC", 0xC3, 1, "カウンタ接点")
    CS = ("CS", 0xC4, 1, "カウンタコイル")
    SB = ("SB", 0xA1, 1, "リンク特殊リレー")
    SM = ("SM", 0x91, 1, "特殊リレー")
    
    # ワードデバイス
    D = ("D", 0xA8, 16, "データレジスタ")
    W = ("W", 0xB4, 16, "リンクレジスタ")
    R = ("R", 0xAF, 16, "ファイルレジスタ")
    ZR = ("ZR", 0xB0, 16, "ファイルレジスタ(拡張)")
    TN = ("TN", 0xC2, 16, "タイマ現在値")
    CN = ("CN", 0xC5, 16, "カウンタ現在値")
    SD = ("SD", 0xA9, 16, "特殊レジスタ")
    SW = ("SW", 0xB5, 16, "リンク特殊レジスタ")
    Z = ("Z", 0xCC, 16, "インデックスレジスタ")
    
    def __init__(self, code: str, device_code: int, bits: int, description: str):
        self.code = code
        self.device_code = device_code
        self.bits = bits
        self.description = description
    
    @property
    def is_bit_device(self) -> bool:
        """ビットデバイスかどうか"""
        return self.bits == 1
    
    @classmethod
    def from_code(cls, code: str) -> Optional['DeviceType']:
        """コードからデバイスタイプを取得"""
        code_upper = code.upper()
        for device in cls:
            if device.code == code_upper:
                return device
        return None


class MCCommand(Enum):
    """MCプロトコルコマンド"""
    BATCH_READ = 0x0401      # 一括読出し
    BATCH_WRITE = 0x1401     # 一括書込み
    RANDOM_READ = 0x0403     # ランダム読出し
    RANDOM_WRITE = 0x1402    # ランダム書込み
    MONITOR = 0x0801         # モニタ登録
    REMOTE_RUN = 0x1001      # リモートRUN
    REMOTE_STOP = 0x1002     # リモートSTOP
    REMOTE_PAUSE = 0x1003    # リモートPAUSE
    REMOTE_RESET = 0x1006    # リモートリセット
    CPU_MODEL_READ = 0x0101  # CPU型名読出し


class MCSubCommand(Enum):
    """MCプロトコルサブコマンド"""
    WORD = 0x0000  # ワード単位
    BIT = 0x0001   # ビット単位


@dataclass
class MCFrame:
    """MCフレームデータ"""
    series: PLCSeries
    network_no: int = 0
    pc_no: int = 0xFF
    request_dest_module_io: int = 0x03FF
    request_dest_module_station: int = 0
    monitoring_timer: int = 0x0010  # 10 = 1秒
    serial_no: int = 0  # 4Eフレーム用


class MCProtocol:
    """MCプロトコル処理クラス"""
    
    # サブヘッダ
    SUBHEADER_3E_REQUEST = 0x5000   # 3Eフレーム要求
    SUBHEADER_3E_RESPONSE = 0xD000  # 3Eフレーム応答
    SUBHEADER_4E_REQUEST = 0x5400   # 4Eフレーム要求
    SUBHEADER_4E_RESPONSE = 0xD400  # 4Eフレーム応答
    
    # 1Eフレームコマンド
    CMD_1E_BATCH_READ_BIT = 0x00     # ビット一括読出し
    CMD_1E_BATCH_READ_WORD = 0x01    # ワード一括読出し
    CMD_1E_BATCH_WRITE_BIT = 0x02    # ビット一括書込み
    CMD_1E_BATCH_WRITE_WORD = 0x03   # ワード一括書込み
    
    @staticmethod
    def build_batch_read_request(
        frame: MCFrame,
        device_type: DeviceType,
        start_address: int,
        count: int,
        is_bit: bool = False
    ) -> bytes:
        """一括読出し要求フレームを構築"""
        command = MCCommand.BATCH_READ.value
        sub_command = MCSubCommand.BIT.value if is_bit else MCSubCommand.WORD.value
        
        # デバイス番号（3バイト） + デバイスコード（1バイト）
        device_data = struct.pack('<I', start_address)[:3] + bytes([device_type.device_code])
        
        # データ部
        data = struct.pack('<HH', command, sub_command) + device_data + struct.pack('<H', count)
        
        return MCProtocol._build_frame(frame, data)
    
    @staticmethod
    def build_batch_write_request(
        frame: MCFrame,
        device_type: DeviceType,
        start_address: int,
        values: List[int],
        is_bit: bool = False
    ) -> bytes:
        """一括書込み要求フレームを構築"""
        command = MCCommand.BATCH_WRITE.value
        sub_command = MCSubCommand.BIT.value if is_bit else MCSubCommand.WORD.value
        
        # デバイス番号（3バイト） + デバイスコード（1バイト）
        device_data = struct.pack('<I', start_address)[:3] + bytes([device_type.device_code])
        
        # データ部の構築
        count = len(values)
        data = struct.pack('<HH', command, sub_command) + device_data + struct.pack('<H', count)
        
        # 値の追加
        if is_bit:
            # ビットデバイス: 1点1バイト（0x00 or 0x01）
            for v in values:
                data += bytes([0x01 if v else 0x00])
        else:
            # ワードデバイス: 1点2バイト
            for v in values:
                data += struct.pack('<H', v & 0xFFFF)
        
        return MCProtocol._build_frame(frame, data)
    
    @staticmethod
    def build_remote_control_request(frame: MCFrame, command: MCCommand) -> bytes:
        """リモート制御要求フレームを構築"""
        if command == MCCommand.REMOTE_RUN:
            # RUN: 強制実行 + クリアモード
            data = struct.pack('<HH', command.value, 0x0000)
            data += struct.pack('<HI', 0x0001, 0x00000000)  # 強制実行、クリアモード
        elif command == MCCommand.REMOTE_STOP:
            data = struct.pack('<HH', command.value, 0x0000)
        elif command == MCCommand.REMOTE_PAUSE:
            data = struct.pack('<HH', command.value, 0x0000)
            data += struct.pack('<H', 0x0001)  # 強制一時停止
        elif command == MCCommand.REMOTE_RESET:
            data = struct.pack('<HH', command.value, 0x0000)
            data += struct.pack('<H', 0x0001)  # 強制リセット
        else:
            data = struct.pack('<HH', command.value, 0x0000)
        
        return MCProtocol._build_frame(frame, data)
    
    @staticmethod
    def build_cpu_model_read_request(frame: MCFrame) -> bytes:
        """CPU型名読出し要求フレームを構築"""
        command = MCCommand.CPU_MODEL_READ.value
        data = struct.pack('<HH', command, 0x0000)
        return MCProtocol._build_frame(frame, data)
    
    @staticmethod
    def _build_frame(frame: MCFrame, data: bytes) -> bytes:
        """フレームを構築"""
        if frame.series == PLCSeries.Q_SERIES:
            return MCProtocol._build_3e_frame(frame, data)
        else:
            return MCProtocol._build_4e_frame(frame, data)
    
    @staticmethod
    def _build_3e_frame(frame: MCFrame, data: bytes) -> bytes:
        """3Eフレームを構築"""
        # サブヘッダ(2) + ネットワーク番号(1) + PC番号(1) + 
        # 要求先ユニットI/O番号(2) + 要求先ユニット局番号(1) + 
        # データ長(2) + 監視タイマ(2) + データ
        
        data_length = len(data) + 2  # 監視タイマ分を含む
        
        header = struct.pack('<H', MCProtocol.SUBHEADER_3E_REQUEST)
        header += struct.pack('<B', frame.network_no)
        header += struct.pack('<B', frame.pc_no)
        header += struct.pack('<H', frame.request_dest_module_io)
        header += struct.pack('<B', frame.request_dest_module_station)
        header += struct.pack('<H', data_length)
        header += struct.pack('<H', frame.monitoring_timer)
        
        return header + data
    
    @staticmethod
    def _build_4e_frame(frame: MCFrame, data: bytes) -> bytes:
        """4Eフレームを構築"""
        # サブヘッダ(2) + シリアル番号(2) + 予約(2) + 
        # ネットワーク番号(1) + PC番号(1) + 
        # 要求先ユニットI/O番号(2) + 要求先ユニット局番号(1) + 
        # データ長(2) + 監視タイマ(2) + データ
        
        data_length = len(data) + 2  # 監視タイマ分を含む
        
        header = struct.pack('<H', MCProtocol.SUBHEADER_4E_REQUEST)
        header += struct.pack('<H', frame.serial_no)
        header += struct.pack('<H', 0x0000)  # 予約
        header += struct.pack('<B', frame.network_no)
        header += struct.pack('<B', frame.pc_no)
        header += struct.pack('<H', frame.request_dest_module_io)
        header += struct.pack('<B', frame.request_dest_module_station)
        header += struct.pack('<H', data_length)
        header += struct.pack('<H', frame.monitoring_timer)
        
        return header + data
    
    @staticmethod
    def parse_response(data: bytes, series: PLCSeries) -> Tuple[int, bytes]:
        """
        レスポンスを解析
        
        Returns:
            (終了コード, データ部)
        """
        if series == PLCSeries.Q_SERIES:
            return MCProtocol._parse_3e_response(data)
        else:
            return MCProtocol._parse_4e_response(data)
    
    @staticmethod
    def _parse_3e_response(data: bytes) -> Tuple[int, bytes]:
        """3Eフレームレスポンスを解析"""
        if len(data) < 11:
            raise ValueError("Invalid 3E response: too short")
        
        # サブヘッダ確認
        subheader = struct.unpack('<H', data[0:2])[0]
        if subheader != MCProtocol.SUBHEADER_3E_RESPONSE:
            raise ValueError(f"Invalid 3E subheader: {subheader:#06x}")
        
        # データ長
        data_length = struct.unpack('<H', data[7:9])[0]
        
        # 終了コード
        end_code = struct.unpack('<H', data[9:11])[0]
        
        # データ部
        response_data = data[11:9+data_length] if data_length > 2 else b''
        
        return end_code, response_data
    
    @staticmethod
    def _parse_4e_response(data: bytes) -> Tuple[int, bytes]:
        """4Eフレームレスポンスを解析"""
        if len(data) < 15:
            raise ValueError("Invalid 4E response: too short")
        
        # サブヘッダ確認
        subheader = struct.unpack('<H', data[0:2])[0]
        if subheader != MCProtocol.SUBHEADER_4E_RESPONSE:
            raise ValueError(f"Invalid 4E subheader: {subheader:#06x}")
        
        # データ長
        data_length = struct.unpack('<H', data[11:13])[0]
        
        # 終了コード
        end_code = struct.unpack('<H', data[13:15])[0]
        
        # データ部
        response_data = data[15:13+data_length] if data_length > 2 else b''
        
        return end_code, response_data
    
    @staticmethod
    def build_response(
        series: PLCSeries,
        end_code: int,
        data: bytes = b'',
        network_no: int = 0,
        pc_no: int = 0xFF,
        serial_no: int = 0,
        frame_type: str = None,
        original_command: int = None
    ) -> bytes:
        """レスポンスフレームを構築（サーバー用）"""
        # フレームタイプに応じてレスポンスを生成
        if frame_type == '1E':
            return MCProtocol._build_1e_response(end_code, data, original_command)
        elif frame_type == '3E_ASCII':
            return MCProtocol._build_3e_ascii_response(end_code, data, network_no, pc_no)
        elif frame_type == '4E_ASCII':
            return MCProtocol._build_4e_ascii_response(end_code, data, network_no, pc_no, serial_no)
        elif series == PLCSeries.Q_SERIES:
            return MCProtocol._build_3e_response(end_code, data, network_no, pc_no)
        else:
            return MCProtocol._build_4e_response(end_code, data, network_no, pc_no, serial_no)
    
    @staticmethod
    def _build_1e_response(end_code: int, data: bytes, original_command: int = None) -> bytes:
        """1Eフレームレスポンスを構築"""
        # 1Eフレームレスポンス: コマンド(1) + 終了コード(1) + データ
        cmd_response = (original_command | 0x80) if original_command is not None else 0x80
        
        if end_code == 0:
            # 正常終了
            return bytes([cmd_response, 0x00]) + data
        else:
            # エラー
            return bytes([cmd_response, end_code & 0xFF]) + struct.pack('<H', end_code)
    
    @staticmethod
    def _build_3e_ascii_response(
        end_code: int,
        data: bytes,
        network_no: int,
        pc_no: int
    ) -> bytes:
        """3E ASCIIレスポンスを構築"""
        # データを16進数文字列に変換
        data_hex = data.hex().upper()
        data_length = len(data) + 2  # 終了コード分
        
        response = f"D000"
        response += f"{network_no:02X}"
        response += f"{pc_no:02X}"
        response += f"03FF"
        response += f"00"
        response += f"{data_length:04X}"
        response += f"{end_code:04X}"
        response += data_hex
        
        return response.encode('ascii')
    
    @staticmethod
    def _build_4e_ascii_response(
        end_code: int,
        data: bytes,
        network_no: int,
        pc_no: int,
        serial_no: int
    ) -> bytes:
        """4E ASCIIレスポンスを構築"""
        data_hex = data.hex().upper()
        data_length = len(data) + 2
        
        response = f"D400"
        response += f"{serial_no:04X}"
        response += f"0000"
        response += f"{network_no:02X}"
        response += f"{pc_no:02X}"
        response += f"03FF"
        response += f"00"
        response += f"{data_length:04X}"
        response += f"{end_code:04X}"
        response += data_hex
        
        return response.encode('ascii')
    
    @staticmethod
    def _build_3e_response(
        end_code: int,
        data: bytes,
        network_no: int,
        pc_no: int
    ) -> bytes:
        """3Eフレームレスポンスを構築"""
        data_length = len(data) + 2  # 終了コード分
        
        response = struct.pack('<H', MCProtocol.SUBHEADER_3E_RESPONSE)
        response += struct.pack('<B', network_no)
        response += struct.pack('<B', pc_no)
        response += struct.pack('<H', 0x03FF)  # 要求先ユニットI/O番号
        response += struct.pack('<B', 0)  # 要求先ユニット局番号
        response += struct.pack('<H', data_length)
        response += struct.pack('<H', end_code)
        response += data
        
        return response
    
    @staticmethod
    def _build_4e_response(
        end_code: int,
        data: bytes,
        network_no: int,
        pc_no: int,
        serial_no: int
    ) -> bytes:
        """4Eフレームレスポンスを構築"""
        data_length = len(data) + 2  # 終了コード分
        
        response = struct.pack('<H', MCProtocol.SUBHEADER_4E_RESPONSE)
        response += struct.pack('<H', serial_no)
        response += struct.pack('<H', 0x0000)  # 予約
        response += struct.pack('<B', network_no)
        response += struct.pack('<B', pc_no)
        response += struct.pack('<H', 0x03FF)
        response += struct.pack('<B', 0)
        response += struct.pack('<H', data_length)
        response += struct.pack('<H', end_code)
        response += data
        
        return response
    
    @staticmethod
    def parse_request(data: bytes) -> dict:
        """
        要求フレームを解析（サーバー用）
        1Eフレーム、3Eフレーム、4Eフレーム、ASCIIフォーマットに対応
        
        対応フォーマット:
        - 3E Binary (サブヘッダ 0x5000): Qシリーズ標準
        - 4E Binary (サブヘッダ 0x5400): iQ-Rシリーズ
        - 3E ASCII (先頭 "5000"): テキストベース
        - 4E ASCII (先頭 "5400"): テキストベース
        - 1E Binary (A互換): 古いQnA/Aシリーズ互換
        - A互換フレーム: 一部のクライアントで使用
        
        Returns:
            解析結果の辞書
        """
        if len(data) < 2:
            raise ValueError("Request too short")
        
        # ASCIIフォーマット判定（印刷可能文字で始まる場合）
        first_chars = data[:4]
        try:
            text_start = first_chars.decode('ascii')
            if text_start in ['5000', '5400', 'D000', 'D400']:
                return MCProtocol._parse_ascii_request(data)
            # その他のASCII開始パターン
            if all(32 <= b < 127 for b in first_chars):
                try:
                    return MCProtocol._parse_ascii_request(data)
                except:
                    pass
        except:
            pass
        
        # バイナリフォーマット判定
        subheader = struct.unpack('<H', data[0:2])[0]
        
        # 3Eフレーム（サブヘッダ 0x5000）
        if subheader == MCProtocol.SUBHEADER_3E_REQUEST:
            if len(data) < 11:
                raise ValueError("3E Request too short")
            return MCProtocol._parse_3e_request(data)
        
        # 4Eフレーム（サブヘッダ 0x5400）
        elif subheader == MCProtocol.SUBHEADER_4E_REQUEST:
            if len(data) < 15:
                raise ValueError("4E Request too short")
            return MCProtocol._parse_4e_request(data)
        
        # 3Eレスポンス形式のリクエスト（一部のクライアントが使用）
        elif subheader == MCProtocol.SUBHEADER_3E_RESPONSE:
            if len(data) >= 11:
                return MCProtocol._parse_3e_request(data)
        
        # 4Eレスポンス形式のリクエスト
        elif subheader == MCProtocol.SUBHEADER_4E_RESPONSE:
            if len(data) >= 15:
                return MCProtocol._parse_4e_request(data)
        
        # 1Eフレーム判定（コマンドコードが0x00-0x0Fの範囲）
        # A互換1Eフレームのコマンド: 0x00-0x03, 0x04-0x07 (ランダム)
        if data[0] <= 0x0F:
            return MCProtocol._parse_1e_request(data)
        
        # FINSプロトコル互換（オムロン系クライアント対策）
        # ヘッダが 0x80 0x00 で始まる場合
        if data[0] == 0x80 and data[1] == 0x00:
            # FINSは非対応だが、エラーを返すためにダミーを返す
            return {
                'series': PLCSeries.Q_SERIES,
                'frame_type': 'FINS_UNSUPPORTED',
                'command': 0x0000,
                'sub_command': 0x0000,
                'command_data': b'',
            }
        
        # その他の場合は1Eフレームとして処理を試みる
        # 多くのシンプルなPLCクライアントは1Eライクなフォーマットを使用
        try:
            return MCProtocol._parse_1e_request(data)
        except:
            raise ValueError(f"Unknown frame format: subheader={subheader:#06x}, first_byte={data[0]:#04x}")
    
    @staticmethod
    def _parse_1e_request(data: bytes) -> dict:
        """
        1Eフレーム要求を解析（QnAシリーズ互換/A互換1Eフレーム）
        
        A互換1Eフレームの構造:
        - コマンド(1) + PC番号(1) + 監視タイマ(2) + 
          デバイスアドレス開始(4) + デバイスコード(2) + 点数(1) [+ 書込データ]
        
        または簡易形式:
        - コマンド(1) + PC番号(1) + 監視タイマ(2) + 
          デバイスアドレス(4) + 点数(1) [+ 書込データ]
        """
        if len(data) < 9:
            raise ValueError("1E Request too short")
        
        command = data[0]
        pc_no = data[1]
        
        # 監視タイマ（2バイト、リトルエンディアン）
        monitoring_timer = struct.unpack('<H', data[2:4])[0]
        
        # 1Eフレームのデバイス指定には複数のパターンがある
        # パターン1: デバイスアドレス(4) + デバイスコード(2) + 点数(1)
        # パターン2: デバイスアドレス(4) + 点数(1) (デバイスはDレジスタ固定)
        # パターン3: デバイス文字(1) + アドレス(3) + 点数(1)
        
        # 1Eフレーム（A互換）のデバイスコードマッピング
        device_code_1e_map = {
            0x4D: 0x90,   # 'M' → M
            0x44: 0xA8,   # 'D' → D
            0x58: 0x9C,   # 'X' → X
            0x59: 0x9D,   # 'Y' → Y
            0x42: 0xA0,   # 'B' → B
            0x57: 0xB4,   # 'W' → W
            0x52: 0xAF,   # 'R' → R
            0x4C: 0x92,   # 'L' → L
            0x46: 0x93,   # 'F' → F
            0x56: 0x94,   # 'V' → V
            0x53: 0x98,   # 'S' → S
            0x5A: 0xCC,   # 'Z' → Z
            # A互換1Eフレームの数値デバイスコード
            0x20: 0xA8,   # D
            0x24: 0xB4,   # W
            0x01: 0x90,   # M
            0x18: 0x9C,   # X (8進)
            0x19: 0x9D,   # Y (8進)
        }
        
        # デバイスコードとアドレスを解析
        device_code = 0xA8  # デフォルトはDレジスタ
        device_addr = 0
        count = 1
        write_data = b''
        
        # 1Eフレームの形式判定
        # - 短いフォーマット: CMD(1) + PC(1) + Timer(2) + Addr(4) + Count(1) [+ Data]
        # - 長いフォーマット: CMD(1) + PC(1) + Timer(2) + Addr(4) + DevCode(2) + Count(1) [+ Data]
        # 
        # 判定方法: 8バイト目がデバイスコードっぽいか点数っぽいかで判断
        # デバイスコードはASCII文字 ('M'=0x4D, 'D'=0x44等) または 0x80以上
        # 点数は通常 1-255 の範囲
        
        byte_8 = data[8] if len(data) > 8 else 0
        
        # 8バイト目がデバイスコードマップに存在するか、0x80以上なら長いフォーマット
        is_long_format = (byte_8 in device_code_1e_map) or (byte_8 >= 0x80)
        
        if is_long_format and len(data) >= 11:
            # 長いフォーマット（デバイスコード付き）
            # デバイスアドレス（4バイト）
            device_addr = struct.unpack('<I', data[4:8])[0]
            
            # デバイスコード（1バイト - ASCIIまたはバイナリ）
            code_byte = data[8]
            if code_byte in device_code_1e_map:
                device_code = device_code_1e_map[code_byte]
            elif code_byte >= 0x80:
                # 3E形式のデバイスコードがそのまま来ている場合
                device_code = code_byte
            
            # 点数（10バイト目）
            count = data[10] if len(data) > 10 else 1
            if count == 0:
                count = 256  # 0は256点を意味する
            
            write_data = data[11:] if len(data) > 11 else b''
        else:
            # 短いフォーマット
            # デバイスアドレス（4バイト）- 上位バイトにデバイスコードが含まれる場合あり
            raw_addr = struct.unpack('<I', data[4:8])[0]
            
            # 上位バイトがASCII文字の場合、デバイスコードとして扱う
            high_byte = (raw_addr >> 24) & 0xFF
            if high_byte in device_code_1e_map:
                device_code = device_code_1e_map[high_byte]
                device_addr = raw_addr & 0x00FFFFFF
            else:
                device_addr = raw_addr
            
            # 点数（8バイト目）
            count = data[8] if len(data) > 8 else 1
            if count == 0:
                count = 256
            
            write_data = data[9:] if len(data) > 9 else b''
        
        # コマンドを3E形式に変換
        if command == 0x00:  # ビット一括読出し
            mc_command = MCCommand.BATCH_READ.value
            sub_command = MCSubCommand.BIT.value
        elif command == 0x01:  # ワード一括読出し
            mc_command = MCCommand.BATCH_READ.value
            sub_command = MCSubCommand.WORD.value
        elif command == 0x02:  # ビット一括書込み
            mc_command = MCCommand.BATCH_WRITE.value
            sub_command = MCSubCommand.BIT.value
            # 書込み時、点数と書込みデータの整合性を確認
            if len(write_data) > 0 and len(write_data) != count:
                # 書込みデータ長から点数を推測
                count = len(write_data)
        elif command == 0x03:  # ワード一括書込み
            mc_command = MCCommand.BATCH_WRITE.value
            sub_command = MCSubCommand.WORD.value
            # 書込み時、点数と書込みデータの整合性を確認
            if len(write_data) >= 2 and (len(write_data) // 2) != count:
                # 書込みデータ長から点数を推測（2バイト/ワード）
                count = len(write_data) // 2
        else:
            mc_command = command
            sub_command = 0
        
        # command_dataを3E形式で構築
        command_data = struct.pack('<I', device_addr)[:3] + bytes([device_code])
        command_data += struct.pack('<H', count)
        
        if command in [0x02, 0x03]:
            command_data += write_data
        
        return {
            'series': PLCSeries.Q_SERIES,
            'frame_type': '1E',
            'network_no': 0,
            'pc_no': pc_no,
            'request_dest_module_io': 0x03FF,
            'request_dest_module_station': 0,
            'data_length': len(data) - 2,
            'monitoring_timer': monitoring_timer,
            'serial_no': 0,
            'command': mc_command,
            'sub_command': sub_command,
            'command_data': command_data,
            'original_command': command,
        }
    
    @staticmethod
    def _parse_ascii_request(data: bytes) -> dict:
        """ASCIIフォーマット要求を解析"""
        try:
            text = data.decode('ascii')
        except:
            raise ValueError("Invalid ASCII format")
        
        # サブヘッダ（4文字）
        subheader = text[0:4]
        
        if subheader == '5000':
            # 3E ASCII
            return MCProtocol._parse_3e_ascii_request(text)
        elif subheader == '5400':
            # 4E ASCII
            return MCProtocol._parse_4e_ascii_request(text)
        else:
            raise ValueError(f"Unknown ASCII subheader: {subheader}")
    
    @staticmethod
    def _parse_3e_ascii_request(text: str) -> dict:
        """3E ASCII要求を解析"""
        # 5000 + ネットワーク番号(2) + PC番号(2) + 要求先(4) + 局番(2) + 
        # データ長(4) + 監視タイマ(4) + コマンド(4) + サブコマンド(4) + データ
        
        result = {
            'series': PLCSeries.Q_SERIES,
            'frame_type': '3E_ASCII',
            'network_no': int(text[4:6], 16),
            'pc_no': int(text[6:8], 16),
            'request_dest_module_io': int(text[8:12], 16),
            'request_dest_module_station': int(text[12:14], 16),
            'data_length': int(text[14:18], 16),
            'monitoring_timer': int(text[18:22], 16),
            'serial_no': 0,
        }
        
        if len(text) >= 30:
            result['command'] = int(text[22:26], 16)
            result['sub_command'] = int(text[26:30], 16)
            
            # デバイス情報を抽出（ASCIIフォーマット）
            # デバイス名(2-4文字) + アドレス(6文字) + 点数(4文字)
            device_part = text[30:]
            result['command_data'] = MCProtocol._parse_ascii_device_data(
                device_part, result['command'], result['sub_command']
            )
        
        return result
    
    @staticmethod
    def _parse_4e_ascii_request(text: str) -> dict:
        """4E ASCII要求を解析"""
        result = {
            'series': PLCSeries.IQR_SERIES,
            'frame_type': '4E_ASCII',
            'serial_no': int(text[4:8], 16),
            'network_no': int(text[12:14], 16),
            'pc_no': int(text[14:16], 16),
            'request_dest_module_io': int(text[16:20], 16),
            'request_dest_module_station': int(text[20:22], 16),
            'data_length': int(text[22:26], 16),
            'monitoring_timer': int(text[26:30], 16),
        }
        
        if len(text) >= 38:
            result['command'] = int(text[30:34], 16)
            result['sub_command'] = int(text[34:38], 16)
            device_part = text[38:]
            result['command_data'] = MCProtocol._parse_ascii_device_data(
                device_part, result['command'], result['sub_command']
            )
        
        return result
    
    @staticmethod
    def _parse_ascii_device_data(device_part: str, command: int, sub_command: int) -> bytes:
        """ASCIIデバイスデータをバイナリに変換"""
        if len(device_part) < 10:
            return b''
        
        # デバイスコード（ASCII 2文字→バイナリコード）
        device_name = device_part[0:2].strip('*').upper()
        device_code = 0xA8  # デフォルトはDレジスタ
        
        device_map = {
            'D': 0xA8, 'W': 0xB4, 'R': 0xAF, 'ZR': 0xB0,
            'M': 0x90, 'X': 0x9C, 'Y': 0x9D, 'B': 0xA0,
            'L': 0x92, 'F': 0x93, 'V': 0x94, 'S': 0x98,
            'TN': 0xC2, 'CN': 0xC5, 'SD': 0xA9, 'SW': 0xB5,
            'TC': 0xC0, 'TS': 0xC1, 'CC': 0xC3, 'CS': 0xC4,
            'SM': 0x91, 'SB': 0xA1, 'Z': 0xCC,
        }
        device_code = device_map.get(device_name, 0xA8)
        
        # アドレス（6文字、16進数）
        try:
            address = int(device_part[2:8], 16)
        except:
            address = 0
        
        # 点数（4文字、16進数）
        try:
            count = int(device_part[8:12], 16)
        except:
            count = 1
        
        # バイナリ形式に変換
        result = struct.pack('<I', address)[:3] + bytes([device_code])
        result += struct.pack('<H', count)
        
        # 書込みデータがある場合
        if command == MCCommand.BATCH_WRITE.value and len(device_part) > 12:
            write_part = device_part[12:]
            if sub_command == MCSubCommand.BIT.value:
                # ビット書込み（1点1文字）
                for c in write_part:
                    result += bytes([1 if c == '1' else 0])
            else:
                # ワード書込み（1点4文字）
                for i in range(0, len(write_part), 4):
                    try:
                        val = int(write_part[i:i+4], 16)
                        result += struct.pack('<H', val)
                    except:
                        break
        
        return result
    
    @staticmethod
    def _parse_3e_request(data: bytes) -> dict:
        """3Eフレーム要求を解析"""
        result = {
            'series': PLCSeries.Q_SERIES,
            'network_no': data[2],
            'pc_no': data[3],
            'request_dest_module_io': struct.unpack('<H', data[4:6])[0],
            'request_dest_module_station': data[6],
            'data_length': struct.unpack('<H', data[7:9])[0],
            'monitoring_timer': struct.unpack('<H', data[9:11])[0],
            'serial_no': 0,
        }
        
        # コマンドとサブコマンド
        if len(data) >= 15:
            result['command'] = struct.unpack('<H', data[11:13])[0]
            result['sub_command'] = struct.unpack('<H', data[13:15])[0]
            result['command_data'] = data[15:]
        
        return result
    
    @staticmethod
    def _parse_4e_request(data: bytes) -> dict:
        """4Eフレーム要求を解析"""
        result = {
            'series': PLCSeries.IQR_SERIES,
            'serial_no': struct.unpack('<H', data[2:4])[0],
            'network_no': data[6],
            'pc_no': data[7],
            'request_dest_module_io': struct.unpack('<H', data[8:10])[0],
            'request_dest_module_station': data[10],
            'data_length': struct.unpack('<H', data[11:13])[0],
            'monitoring_timer': struct.unpack('<H', data[13:15])[0],
        }
        
        # コマンドとサブコマンド
        if len(data) >= 19:
            result['command'] = struct.unpack('<H', data[15:17])[0]
            result['sub_command'] = struct.unpack('<H', data[17:19])[0]
            result['command_data'] = data[19:]
        
        return result


# エラーコード定義
MC_ERROR_CODES = {
    0x0000: "正常完了",
    0x0050: "コマンド・サブコマンド指定エラー",
    0x0051: "CPU間通信エラー",
    0x0052: "CPUがスタンバイ中",
    0x0054: "書込禁止",
    0x0055: "要求データ長エラー",
    0x0058: "要求不可",
    0x0059: "コマンド実行不可",
    0xC050: "デバイス指定エラー",
    0xC051: "デバイス範囲外",
    0xC052: "要求点数範囲外",
    0xC053: "ビットデバイス点数エラー",
    0xC054: "開始デバイスエラー",
    0xC056: "デバイス拡張指定エラー",
    0xC058: "デバイスアドレス範囲外",
    0xC059: "モニタ登録点数オーバー",
}


def get_error_message(code: int) -> str:
    """エラーコードからメッセージを取得"""
    return MC_ERROR_CODES.get(code, f"不明なエラー ({code:#06x})")
