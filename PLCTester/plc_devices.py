"""
PLCデバイス管理
三菱PLCの全デバイスタイプを管理
"""
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import threading

from mc_protocol import DeviceType


@dataclass
class DeviceRange:
    """デバイス範囲定義"""
    min_address: int
    max_address: int
    description: str = ""


class PLCDeviceManager:
    """
    PLCデバイス管理クラス
    
    全デバイスタイプのメモリを管理し、読み書きを提供
    """
    
    # デバイス範囲定義（Qシリーズ標準）
    DEVICE_RANGES_Q = {
        DeviceType.D: DeviceRange(0, 12287, "データレジスタ"),
        DeviceType.M: DeviceRange(0, 8191, "内部リレー"),
        DeviceType.Y: DeviceRange(0, 0x1FFF, "出力（16進）"),
        DeviceType.X: DeviceRange(0, 0x1FFF, "入力（16進）"),
        DeviceType.B: DeviceRange(0, 0x7FFF, "リンクリレー（16進）"),
        DeviceType.W: DeviceRange(0, 0x7FFF, "リンクレジスタ（16進）"),
        DeviceType.L: DeviceRange(0, 8191, "ラッチリレー"),
        DeviceType.F: DeviceRange(0, 2047, "アナンシエータ"),
        DeviceType.V: DeviceRange(0, 2047, "エッジリレー"),
        DeviceType.S: DeviceRange(0, 8191, "ステップリレー"),
        DeviceType.R: DeviceRange(0, 32767, "ファイルレジスタ"),
        DeviceType.ZR: DeviceRange(0, 0xFFFFF, "拡張ファイルレジスタ"),
        DeviceType.TN: DeviceRange(0, 2047, "タイマ現在値"),
        DeviceType.TC: DeviceRange(0, 2047, "タイマ接点"),
        DeviceType.TS: DeviceRange(0, 2047, "タイマコイル"),
        DeviceType.CN: DeviceRange(0, 1023, "カウンタ現在値"),
        DeviceType.CC: DeviceRange(0, 1023, "カウンタ接点"),
        DeviceType.CS: DeviceRange(0, 1023, "カウンタコイル"),
        DeviceType.SM: DeviceRange(0, 2047, "特殊リレー"),
        DeviceType.SD: DeviceRange(0, 2047, "特殊レジスタ"),
        DeviceType.SB: DeviceRange(0, 0x7FF, "リンク特殊リレー"),
        DeviceType.SW: DeviceRange(0, 0x7FF, "リンク特殊レジスタ"),
        DeviceType.Z: DeviceRange(0, 19, "インデックスレジスタ"),
    }
    
    # デバイス範囲定義（iQ-Rシリーズ標準）
    DEVICE_RANGES_IQR = {
        DeviceType.D: DeviceRange(0, 65535, "データレジスタ"),
        DeviceType.M: DeviceRange(0, 65535, "内部リレー"),
        DeviceType.Y: DeviceRange(0, 0x1FFF, "出力（16進）"),
        DeviceType.X: DeviceRange(0, 0x1FFF, "入力（16進）"),
        DeviceType.B: DeviceRange(0, 0x7FFF, "リンクリレー（16進）"),
        DeviceType.W: DeviceRange(0, 0xFFFF, "リンクレジスタ（16進）"),
        DeviceType.L: DeviceRange(0, 32767, "ラッチリレー"),
        DeviceType.F: DeviceRange(0, 32767, "アナンシエータ"),
        DeviceType.V: DeviceRange(0, 32767, "エッジリレー"),
        DeviceType.S: DeviceRange(0, 8191, "ステップリレー"),
        DeviceType.R: DeviceRange(0, 32767, "ファイルレジスタ"),
        DeviceType.ZR: DeviceRange(0, 0xFFFFFFF, "拡張ファイルレジスタ"),
        DeviceType.TN: DeviceRange(0, 2047, "タイマ現在値"),
        DeviceType.TC: DeviceRange(0, 2047, "タイマ接点"),
        DeviceType.TS: DeviceRange(0, 2047, "タイマコイル"),
        DeviceType.CN: DeviceRange(0, 1023, "カウンタ現在値"),
        DeviceType.CC: DeviceRange(0, 1023, "カウンタ接点"),
        DeviceType.CS: DeviceRange(0, 1023, "カウンタコイル"),
        DeviceType.SM: DeviceRange(0, 4095, "特殊リレー"),
        DeviceType.SD: DeviceRange(0, 4095, "特殊レジスタ"),
        DeviceType.SB: DeviceRange(0, 0x7FF, "リンク特殊リレー"),
        DeviceType.SW: DeviceRange(0, 0x7FF, "リンク特殊レジスタ"),
        DeviceType.Z: DeviceRange(0, 19, "インデックスレジスタ"),
    }
    
    def __init__(self, is_iqr: bool = False):
        """
        初期化
        
        Args:
            is_iqr: iQ-Rシリーズの場合True
        """
        self.is_iqr = is_iqr
        self.device_ranges = self.DEVICE_RANGES_IQR if is_iqr else self.DEVICE_RANGES_Q
        
        # デバイスメモリ（デバイスタイプ -> アドレス -> 値）
        self._memory: Dict[DeviceType, Dict[int, int]] = {}
        
        # スレッドセーフのためのロック
        self._lock = threading.RLock()
        
        # メモリ初期化
        self._initialize_memory()
    
    def _initialize_memory(self):
        """メモリを初期化"""
        with self._lock:
            for device_type in self.device_ranges:
                self._memory[device_type] = {}
    
    def clear_all(self):
        """全メモリをクリア"""
        with self._lock:
            self._initialize_memory()
    
    def clear_device(self, device_type: DeviceType):
        """特定デバイスのメモリをクリア"""
        with self._lock:
            if device_type in self._memory:
                self._memory[device_type] = {}
    
    def validate_address(self, device_type: DeviceType, address: int) -> bool:
        """アドレスが有効か確認"""
        if device_type not in self.device_ranges:
            return False
        
        range_def = self.device_ranges[device_type]
        return range_def.min_address <= address <= range_def.max_address
    
    def validate_range(self, device_type: DeviceType, start: int, count: int) -> bool:
        """アドレス範囲が有効か確認"""
        if not self.validate_address(device_type, start):
            return False
        if not self.validate_address(device_type, start + count - 1):
            return False
        return True
    
    # === ビットデバイス操作 ===
    
    def get_bit(self, device_type: DeviceType, address: int) -> bool:
        """ビットを読み出し"""
        with self._lock:
            if device_type not in self._memory:
                return False
            return bool(self._memory[device_type].get(address, 0))
    
    def set_bit(self, device_type: DeviceType, address: int, value: bool) -> bool:
        """ビットを書き込み"""
        if not self.validate_address(device_type, address):
            return False
        
        with self._lock:
            if device_type not in self._memory:
                self._memory[device_type] = {}
            self._memory[device_type][address] = 1 if value else 0
        return True
    
    def get_bits(self, device_type: DeviceType, start: int, count: int) -> List[bool]:
        """複数ビットを読み出し"""
        with self._lock:
            result = []
            for i in range(count):
                result.append(self.get_bit(device_type, start + i))
            return result
    
    def set_bits(self, device_type: DeviceType, start: int, values: List[bool]) -> bool:
        """複数ビットを書き込み"""
        if not self.validate_range(device_type, start, len(values)):
            return False
        
        with self._lock:
            for i, value in enumerate(values):
                self.set_bit(device_type, start + i, value)
        return True
    
    # === ワードデバイス操作 ===
    
    def get_word(self, device_type: DeviceType, address: int) -> int:
        """ワードを読み出し"""
        with self._lock:
            if device_type not in self._memory:
                return 0
            return self._memory[device_type].get(address, 0) & 0xFFFF
    
    def set_word(self, device_type: DeviceType, address: int, value: int) -> bool:
        """ワードを書き込み"""
        if not self.validate_address(device_type, address):
            return False
        
        with self._lock:
            if device_type not in self._memory:
                self._memory[device_type] = {}
            self._memory[device_type][address] = value & 0xFFFF
        return True
    
    def get_words(self, device_type: DeviceType, start: int, count: int) -> List[int]:
        """複数ワードを読み出し"""
        with self._lock:
            result = []
            for i in range(count):
                result.append(self.get_word(device_type, start + i))
            return result
    
    def set_words(self, device_type: DeviceType, start: int, values: List[int]) -> bool:
        """複数ワードを書き込み"""
        if not self.validate_range(device_type, start, len(values)):
            return False
        
        with self._lock:
            for i, value in enumerate(values):
                self.set_word(device_type, start + i, value)
        return True
    
    # === ダブルワード操作 ===
    
    def get_dword(self, device_type: DeviceType, address: int) -> int:
        """ダブルワードを読み出し（2ワード）"""
        with self._lock:
            low = self.get_word(device_type, address)
            high = self.get_word(device_type, address + 1)
            return (high << 16) | low
    
    def set_dword(self, device_type: DeviceType, address: int, value: int) -> bool:
        """ダブルワードを書き込み（2ワード）"""
        low = value & 0xFFFF
        high = (value >> 16) & 0xFFFF
        
        if not self.set_word(device_type, address, low):
            return False
        return self.set_word(device_type, address + 1, high)
    
    # === 文字列操作 ===
    
    def get_string(self, device_type: DeviceType, start: int, length: int) -> str:
        """文字列を読み出し"""
        with self._lock:
            words = self.get_words(device_type, start, (length + 1) // 2)
            chars = []
            for word in words:
                chars.append(chr(word & 0xFF))
                chars.append(chr((word >> 8) & 0xFF))
            return ''.join(chars[:length]).rstrip('\x00')
    
    def set_string(self, device_type: DeviceType, start: int, text: str, length: int) -> bool:
        """文字列を書き込み"""
        # 指定長に合わせる
        text = text.ljust(length, '\x00')[:length]
        
        words = []
        for i in range(0, len(text), 2):
            low = ord(text[i]) if i < len(text) else 0
            high = ord(text[i + 1]) if i + 1 < len(text) else 0
            words.append((high << 8) | low)
        
        return self.set_words(device_type, start, words)
    
    # === ビットデバイスをワードとして読み書き ===
    
    def get_bit_as_word(self, device_type: DeviceType, start: int) -> int:
        """16ビットをワードとして読み出し"""
        with self._lock:
            result = 0
            for i in range(16):
                if self.get_bit(device_type, start + i):
                    result |= (1 << i)
            return result
    
    def set_bit_from_word(self, device_type: DeviceType, start: int, value: int) -> bool:
        """ワード値を16ビットとして書き込み"""
        with self._lock:
            for i in range(16):
                self.set_bit(device_type, start + i, bool(value & (1 << i)))
        return True
    
    # === デバッグ・情報取得 ===
    
    def get_device_info(self) -> Dict[str, Any]:
        """デバイス情報を取得"""
        info = {}
        with self._lock:
            for device_type, mem in self._memory.items():
                non_zero = {k: v for k, v in mem.items() if v != 0}
                if non_zero:
                    info[device_type.code] = {
                        'count': len(non_zero),
                        'addresses': list(non_zero.keys())[:10]  # 最初の10個
                    }
        return info
    
    def dump_device(self, device_type: DeviceType, start: int, count: int) -> Dict[int, int]:
        """デバイスのダンプを取得"""
        result = {}
        with self._lock:
            for i in range(count):
                addr = start + i
                if device_type.is_bit_device:
                    result[addr] = 1 if self.get_bit(device_type, addr) else 0
                else:
                    result[addr] = self.get_word(device_type, addr)
        return result
    
    def import_values(self, data: Dict[str, Dict[int, int]]):
        """値を一括インポート"""
        with self._lock:
            for device_code, values in data.items():
                device_type = DeviceType.from_code(device_code)
                if device_type:
                    for addr, val in values.items():
                        if device_type.is_bit_device:
                            self.set_bit(device_type, addr, bool(val))
                        else:
                            self.set_word(device_type, addr, val)
    
    def export_values(self) -> Dict[str, Dict[int, int]]:
        """値を一括エクスポート"""
        result = {}
        with self._lock:
            for device_type, mem in self._memory.items():
                if mem:
                    result[device_type.code] = dict(mem)
        return result
