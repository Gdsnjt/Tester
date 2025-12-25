"""
GigE Visionプロトコル実装
GVCP (GigE Vision Control Protocol) および GVSP (GigE Vision Streaming Protocol)

参考: GigE Vision Specification v2.0
"""
import struct
from enum import IntEnum
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import socket


# ========================================
# GVCP - GigE Vision Control Protocol
# ========================================

class GVCPCommand(IntEnum):
    """GVCPコマンド"""
    DISCOVERY_CMD = 0x0002
    DISCOVERY_ACK = 0x0003
    FORCEIP_CMD = 0x0004
    FORCEIP_ACK = 0x0005
    PACKETRESEND_CMD = 0x0040
    PACKETRESEND_ACK = 0x0041
    READREG_CMD = 0x0080
    READREG_ACK = 0x0081
    WRITEREG_CMD = 0x0082
    WRITEREG_ACK = 0x0083
    READMEM_CMD = 0x0084
    READMEM_ACK = 0x0085
    WRITEMEM_CMD = 0x0086
    WRITEMEM_ACK = 0x0087
    PENDING_ACK = 0x0089
    EVENT_CMD = 0x00C0
    EVENT_ACK = 0x00C1
    EVENTDATA_CMD = 0x00C2
    EVENTDATA_ACK = 0x00C3
    ACTION_CMD = 0x0100
    ACTION_ACK = 0x0101


class GVCPStatus(IntEnum):
    """GVCPステータスコード"""
    SUCCESS = 0x0000
    PACKET_RESEND = 0x0100
    NOT_IMPLEMENTED = 0x8001
    INVALID_PARAMETER = 0x8002
    INVALID_ADDRESS = 0x8003
    WRITE_PROTECT = 0x8004
    BAD_ALIGNMENT = 0x8005
    ACCESS_DENIED = 0x8006
    BUSY = 0x8007
    LOCAL_PROBLEM = 0x8008
    MSG_MISMATCH = 0x8009
    INVALID_PROTOCOL = 0x800A
    NO_MSG = 0x800B
    PACKET_UNAVAILABLE = 0x800C
    DATA_OVERRUN = 0x800D
    INVALID_HEADER = 0x800E
    WRONG_CONFIG = 0x800F
    PACKET_NOT_YET_AVAILABLE = 0x8010
    PACKET_ALREADY_RESENT = 0x8011
    PACKET_AND_PREV_REMOVED = 0x8012
    ERROR = 0x8FFF


# ========================================
# Bootstrap Registers
# ========================================

class BootstrapRegister(IntEnum):
    """標準ブートストラップレジスタアドレス"""
    # 基本情報
    VERSION = 0x0000
    DEVICE_MODE = 0x0004
    DEVICE_MAC_HIGH = 0x0008
    DEVICE_MAC_LOW = 0x000C
    SUPPORTED_IP_CONFIG = 0x0010
    CURRENT_IP_CONFIG = 0x0014
    CURRENT_IP = 0x0024
    CURRENT_SUBNET = 0x0034
    CURRENT_GATEWAY = 0x0044
    
    # 製造者情報
    MANUFACTURER_NAME = 0x0048
    MODEL_NAME = 0x0068
    DEVICE_VERSION = 0x0088
    MANUFACTURER_INFO = 0x00A8
    SERIAL_NUMBER = 0x00D8
    USER_DEFINED_NAME = 0x00E8
    
    # XML情報
    FIRST_URL = 0x0200
    SECOND_URL = 0x0400
    
    # ストリーミング制御
    STREAM_CHANNEL_COUNT = 0x0904
    STREAM_CHANNEL_0_PORT = 0x0D00
    STREAM_CHANNEL_0_PACKET_SIZE = 0x0D04
    STREAM_CHANNEL_0_PACKET_DELAY = 0x0D08
    STREAM_CHANNEL_0_DEST_IP = 0x0D18
    
    # 制御チャネル
    CONTROL_CHANNEL_PRIVILEGE = 0x0A00
    HEARTBEAT_TIMEOUT = 0x0938
    
    # 取得制御
    ACQUISITION_START = 0x0124
    ACQUISITION_STOP = 0x0128


# ========================================
# GVSP - GigE Vision Streaming Protocol
# ========================================

class GVSPPacketType(IntEnum):
    """GVSPパケットタイプ"""
    DATA_LEADER = 1
    DATA_TRAILER = 2
    DATA_PAYLOAD = 3
    ALL_IN = 4


class GVSPPayloadType(IntEnum):
    """GVSPペイロードタイプ"""
    IMAGE = 0x0001
    RAW_DATA = 0x0002
    FILE = 0x0003
    CHUNK_DATA = 0x0004
    EXTENDED_CHUNK_DATA = 0x0005
    JPEG = 0x0006
    JPEG2000 = 0x0007
    H264 = 0x0008
    MULTI_ZONE_IMAGE = 0x0009


class PixelFormat(IntEnum):
    """ピクセルフォーマット"""
    MONO8 = 0x01080001
    MONO10 = 0x01100003
    MONO12 = 0x01100005
    MONO16 = 0x01100007
    BGR8 = 0x02180014
    RGB8 = 0x02180014  # BGR8と同じコード
    BAYERBG8 = 0x0108000B
    BAYERGB8 = 0x0108000A
    BAYERRG8 = 0x01080009
    BAYERGR8 = 0x01080008


# ========================================
# パケット構造体
# ========================================

@dataclass
class GVCPHeader:
    """GVCPパケットヘッダ"""
    key: int = 0x42  # Magic key
    flag: int = 0x01  # Request: 0x01, Acknowledge: 0x00
    command: int = 0
    length: int = 0
    req_id: int = 0
    
    def pack(self) -> bytes:
        """バイナリにパック"""
        return struct.pack('>BBHHH', 
                          self.key, self.flag, self.command, 
                          self.length, self.req_id)
    
    @classmethod
    def unpack(cls, data: bytes) -> 'GVCPHeader':
        """バイナリからアンパック"""
        if len(data) < 8:
            raise ValueError(f"GVCPヘッダが短すぎます: {len(data)} bytes")
        key, flag, command, length, req_id = struct.unpack('>BBHHH', data[:8])
        return cls(key=key, flag=flag, command=command, length=length, req_id=req_id)


@dataclass
class GVCPAckHeader:
    """GVCP ACKパケットヘッダ"""
    status: int = 0
    command: int = 0
    length: int = 0
    ack_id: int = 0
    
    def pack(self) -> bytes:
        """バイナリにパック"""
        return struct.pack('>HHHH', 
                          self.status, self.command, 
                          self.length, self.ack_id)
    
    @classmethod
    def unpack(cls, data: bytes) -> 'GVCPAckHeader':
        """バイナリからアンパック"""
        if len(data) < 8:
            raise ValueError(f"GVCP ACKヘッダが短すぎます: {len(data)} bytes")
        status, command, length, ack_id = struct.unpack('>HHHH', data[:8])
        return cls(status=status, command=command, length=length, ack_id=ack_id)


@dataclass
class GVSPHeader:
    """GVSPパケットヘッダ"""
    status: int = 0
    block_id: int = 0
    packet_format: int = 0
    packet_id: int = 0
    
    def pack(self) -> bytes:
        """バイナリにパック（8バイト）"""
        # Format: status(2) + block_id(2) + format(1) + packet_id(3)
        packet_id_bytes = self.packet_id.to_bytes(3, 'big')
        return struct.pack('>HHB', self.status, self.block_id, self.packet_format) + packet_id_bytes
    
    @classmethod
    def unpack(cls, data: bytes) -> 'GVSPHeader':
        """バイナリからアンパック"""
        if len(data) < 8:
            raise ValueError(f"GVSPヘッダが短すぎます: {len(data)} bytes")
        status, block_id, packet_format = struct.unpack('>HHB', data[:5])
        packet_id = int.from_bytes(data[5:8], 'big')
        return cls(status=status, block_id=block_id, 
                  packet_format=packet_format, packet_id=packet_id)


@dataclass
class ImageLeader:
    """画像リーダーパケットデータ"""
    payload_type: int = GVSPPayloadType.IMAGE
    timestamp: int = 0
    pixel_format: int = PixelFormat.MONO8
    width: int = 640
    height: int = 480
    offset_x: int = 0
    offset_y: int = 0
    padding_x: int = 0
    padding_y: int = 0
    
    def pack(self) -> bytes:
        """バイナリにパック（36バイト）"""
        return struct.pack('>HQIIIHHII',
                          self.payload_type,
                          self.timestamp,
                          self.pixel_format,
                          self.width,
                          self.height,
                          self.offset_x,
                          self.offset_y,
                          self.padding_x,
                          self.padding_y)


@dataclass
class ImageTrailer:
    """画像トレーラーパケットデータ"""
    payload_type: int = GVSPPayloadType.IMAGE
    size_y: int = 480
    
    def pack(self) -> bytes:
        """バイナリにパック（8バイト）"""
        return struct.pack('>HxxI', self.payload_type, self.size_y)


# ========================================
# ユーティリティ関数
# ========================================

def ip_to_int(ip_str: str) -> int:
    """IPアドレス文字列を整数に変換"""
    parts = [int(p) for p in ip_str.split('.')]
    return (parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8) | parts[3]


def int_to_ip(ip_int: int) -> str:
    """整数をIPアドレス文字列に変換"""
    return f"{(ip_int >> 24) & 0xFF}.{(ip_int >> 16) & 0xFF}.{(ip_int >> 8) & 0xFF}.{ip_int & 0xFF}"


def mac_to_bytes(mac_str: str) -> bytes:
    """MACアドレス文字列をバイト列に変換"""
    parts = mac_str.replace(':', '-').split('-')
    return bytes(int(p, 16) for p in parts)


def bytes_to_mac(mac_bytes: bytes) -> str:
    """バイト列をMACアドレス文字列に変換"""
    return ':'.join(f'{b:02X}' for b in mac_bytes)


def pad_string(s: str, length: int) -> bytes:
    """文字列を指定長にパディング"""
    encoded = s.encode('utf-8')[:length]
    return encoded.ljust(length, b'\x00')


def get_local_ip() -> str:
    """ローカルIPアドレスを取得"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


def get_local_mac() -> str:
    """ローカルMACアドレスを取得（ダミー）"""
    import uuid
    mac = uuid.getnode()
    return ':'.join(f'{(mac >> i) & 0xFF:02X}' for i in range(40, -8, -8))
