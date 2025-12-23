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
        serial_no: int = 0
    ) -> bytes:
        """レスポンスフレームを構築（サーバー用）"""
        if series == PLCSeries.Q_SERIES:
            return MCProtocol._build_3e_response(end_code, data, network_no, pc_no)
        else:
            return MCProtocol._build_4e_response(end_code, data, network_no, pc_no, serial_no)
    
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
        
        Returns:
            解析結果の辞書
        """
        if len(data) < 11:
            raise ValueError("Request too short")
        
        subheader = struct.unpack('<H', data[0:2])[0]
        
        if subheader == MCProtocol.SUBHEADER_3E_REQUEST:
            return MCProtocol._parse_3e_request(data)
        elif subheader == MCProtocol.SUBHEADER_4E_REQUEST:
            return MCProtocol._parse_4e_request(data)
        else:
            raise ValueError(f"Unknown subheader: {subheader:#06x}")
    
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
