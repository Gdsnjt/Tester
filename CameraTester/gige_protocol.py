"""
GigE Vision Protocol Implementation
GVCP (GigE Vision Control Protocol) and GVSP (GigE Vision Streaming Protocol)
"""
import struct
import socket
import threading
import time
import logging
from enum import IntEnum
from typing import Optional, Tuple, Dict, List
from dataclasses import dataclass

# ログ設定
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('gige_protocol.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class GVCPCommand(IntEnum):
    """GVCP Command codes"""
    DISCOVERY_CMD = 0x0002
    DISCOVERY_ACK = 0x0003
    READREG_CMD = 0x0080
    READREG_ACK = 0x0081
    WRITEREG_CMD = 0x0082
    WRITEREG_ACK = 0x0083
    READMEM_CMD = 0x0084
    READMEM_ACK = 0x0085
    WRITEMEM_CMD = 0x0086
    WRITEMEM_ACK = 0x0087


class GVCPStatus(IntEnum):
    """GVCP Status codes"""
    SUCCESS = 0x0000
    NOT_IMPLEMENTED = 0x8001
    INVALID_PARAMETER = 0x8002
    INVALID_ADDRESS = 0x8003
    WRITE_PROTECT = 0x8004
    BAD_ALIGNMENT = 0x8005
    ACCESS_DENIED = 0x8006
    BUSY = 0x8007
    ERROR = 0x8FFF


class GVSPPixelType(IntEnum):
    """GVSP Pixel format types"""
    MONO8 = 0x01080001
    MONO16 = 0x01100007
    RGB8 = 0x02180014
    BGR8 = 0x02180015


@dataclass
class GVCPPacket:
    """GVCP Packet structure"""
    command: int      # 2 bytes
    length: int       # 2 bytes
    request_id: int   # 2 bytes
    data: bytes = b''


@dataclass
class GVSPPacket:
    """GVSP Packet structure"""
    packet_id: int
    block_id: int
    packet_format: int
    data: bytes = b''


class BootstrapRegister:
    """GigE Vision Bootstrap Registers (0x0000-0x0A00)"""
    VERSION = 0x0000
    DEVICE_MODE = 0x0004
    DEVICE_MAC_HIGH = 0x0008
    DEVICE_MAC_LOW = 0x000C
    SUPPORTED_IP_CONFIG = 0x0010
    CURRENT_IP_CONFIG = 0x0014
    CURRENT_IP_ADDRESS = 0x0024
    CURRENT_SUBNET_MASK = 0x0034
    CURRENT_GATEWAY = 0x0044
    MANUFACTURER_NAME = 0x0048
    MODEL_NAME = 0x0068
    DEVICE_VERSION = 0x0088
    MANUFACTURER_INFO = 0x00A8
    SERIAL_NUMBER = 0x00D8
    USER_DEFINED_NAME = 0x00E8
    FIRST_URL = 0x0200
    SECOND_URL = 0x0400
    NUMBER_NETWORK_INTERFACES = 0x0600
    PERSISTENT_IP_ADDRESS = 0x064C
    PERSISTENT_SUBNET_MASK = 0x065C
    PERSISTENT_GATEWAY = 0x066C
    LINK_SPEED = 0x0600
    MESSAGE_CHANNEL_PORT = 0x0900
    STREAM_CHANNEL_PORT = 0x0D00
    NUMBER_STREAM_CHANNELS = 0x0904
    HEARTBEAT_TIMEOUT = 0x0938
    GVCP_CONFIGURATION = 0x0954
    DISCOVERY_ACK_DELAY = 0x0958
    GVCP_CAPABILITY = 0x092C
    CAPABILITY = 0x0934
    CONTROL_SWITCHOVER_KEY = 0x0940
    GVSP_CONFIGURATION = 0x0A00
    PHYSICAL_LINK_CONFIGURATION = 0x0A04
    IEEE_1588_STATUS = 0x0A08
    SCHEDULED_ACTION_COMMAND_QUEUE_SIZE = 0x0A0C


class GVCPServer:
    """GigE Vision Control Protocol Server"""
    
    def __init__(self, device_info: Dict[str, str], bind_ip: str = "0.0.0.0", port: int = 3956, gvsp_port: int = 50000):
        self.device_info = device_info
        self.bind_ip = bind_ip
        self.port = port
        self.gvsp_port = gvsp_port
        self.socket: Optional[socket.socket] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.registers: Dict[int, bytes] = {}
        self._init_registers()
    
    def _init_registers(self):
        """ブートストラップレジスタの初期化"""
        def str_to_bytes(s: str, length: int) -> bytes:
            return s.encode('ascii').ljust(length, b'\x00')[:length]
        
        self.registers[BootstrapRegister.VERSION] = struct.pack('>I', 0x00010200)
        self.registers[BootstrapRegister.MANUFACTURER_NAME] = str_to_bytes(
            self.device_info.get('vendor', 'MockCam'), 32)
        self.registers[BootstrapRegister.MODEL_NAME] = str_to_bytes(
            self.device_info.get('model', 'VirtualCam-1'), 32)
        self.registers[BootstrapRegister.DEVICE_VERSION] = str_to_bytes('1.0.0', 32)
        self.registers[BootstrapRegister.MANUFACTURER_INFO] = str_to_bytes('Mock GigE Camera', 48)
        self.registers[BootstrapRegister.SERIAL_NUMBER] = str_to_bytes(
            self.device_info.get('serial', 'MOCK001'), 16)
        self.registers[BootstrapRegister.USER_DEFINED_NAME] = str_to_bytes(
            self.device_info.get('user_name', 'TestCamera'), 16)
        
        # local_ipをdevice_infoから取得
        local_ip = self.device_info.get('local_ip', '192.168.1.100')
        ip_parts = local_ip.split('.')
        if len(ip_parts) == 4:
            ip_bytes = bytes([int(p) for p in ip_parts])
            self.registers[BootstrapRegister.CURRENT_IP_ADDRESS] = ip_bytes
        else:
            self.registers[BootstrapRegister.CURRENT_IP_ADDRESS] = bytes([192, 168, 1, 100])
        
        self.registers[BootstrapRegister.CURRENT_SUBNET_MASK] = bytes([255, 255, 255, 0])
        self.registers[BootstrapRegister.CURRENT_GATEWAY] = bytes([192, 168, 1, 1])
        self.registers[BootstrapRegister.MESSAGE_CHANNEL_PORT] = struct.pack('>I', self.port)
        self.registers[BootstrapRegister.STREAM_CHANNEL_PORT] = struct.pack('>I', self.gvsp_port)
        self.registers[BootstrapRegister.NUMBER_STREAM_CHANNELS] = struct.pack('>I', 1)
        self.registers[BootstrapRegister.HEARTBEAT_TIMEOUT] = struct.pack('>I', 3000)
    
    def start(self):
        """GVCPサーバーを起動"""
        if self.running:
            return
        
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Windowsで複数のソケットが同じポートにバインドできるようにする
        if hasattr(socket, 'SO_REUSEPORT'):
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        # ブロードキャストパケットを受信できるようにする
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.socket.bind((self.bind_ip, self.port))
        
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        
        print(f"[GVCP] Server started on {self.bind_ip}:{self.port}")
    
    def stop(self):
        """Stop GVCP server"""
        self.running = False
        if self.socket:
            self.socket.close()
        if self.thread:
            self.thread.join(timeout=2.0)
        print("[GVCP] Server stopped")
    
    def _run(self):
        """Main server loop"""
        logger.info(f"GVCP listening on port {self.port}")
        while self.running:
            try:
                data, addr = self.socket.recvfrom(1500)
                logger.debug(f"Packet received: {len(data)} bytes from {addr[0]}:{addr[1]}")
                logger.debug(f"Packet dump: {data[:16].hex(' ')}")
                
                # GVCPパケットの最小サイズをチェック（ヘッダー8バイト）
                if len(data) < 8:
                    logger.debug(f"Packet too small: {len(data)} bytes")
                    continue
                
                packet = self._parse_packet(data)
                if packet is None:
                    logger.debug("Packet parse failed")
                    continue
                
                response = self._handle_command(packet, addr)
                
                if response:
                    self.socket.sendto(response, addr)
                    logger.debug(f"Response sent: {len(response)} bytes to {addr[0]}:{addr[1]}")
            
            except Exception as e:
                if self.running:
                    logger.error(f"Error: {e}")
    
    def _parse_packet(self, data: bytes) -> Optional[GVCPPacket]:
        """GVCPパケットを解析
        
        Args:
            data: 受信データ
            
        Returns:
            GVCPPacket または None（解析失敗時）
        """
        try:
            if len(data) < 8:
                return None
            
            # GVCPヘッダー: Magic(1) + Flags(1) + Command(2) + Length(2) + ReqID(2) = 8バイト
            magic, flags, command, length, request_id = struct.unpack('>BBHHH', data[:8])
            packet_data = data[8:]
            
            logger.debug(f"Parsed: magic=0x{magic:02x}, flags=0x{flags:02x}, cmd=0x{command:04x}, len={length}, req_id=0x{request_id:04x}")
            
            # Magic byteチェック (0x42 = GigE Vision)
            if magic != 0x42:
                logger.warning(f"Invalid magic byte: 0x{magic:02x}")
                return None
            
            return GVCPPacket(command, length, request_id, packet_data)
        except struct.error as e:
            logger.error(f"struct.error: {e}")
            return None
        except Exception as e:
            logger.error(f"Parse error: {e}")
            return None
    
    def _handle_command(self, packet: GVCPPacket, addr: Tuple[str, int]) -> Optional[bytes]:
        """Handle GVCP command"""
        if packet.command == GVCPCommand.DISCOVERY_CMD:
            logger.info(f"Discovery request from {addr[0]}:{addr[1]}")
            print(f"[GVCP] Discovery from {addr[0]}")
            return self._handle_discovery(packet)
        elif packet.command == GVCPCommand.READREG_CMD:
            return self._handle_readreg(packet)
        elif packet.command == GVCPCommand.WRITEREG_CMD:
            return self._handle_writereg(packet)
        elif packet.command == GVCPCommand.READMEM_CMD:
            return self._handle_readmem(packet)
        return None
    
    def _handle_discovery(self, packet: GVCPPacket) -> bytes:
        """ディスカバリーコマンドを処理"""
        # DISCOVERY_ACKヘッダー: Magic(1) + Flags(1) + Command(2) + Length(2) + ReqID(2)
        # ACKデータは、レジスタ情報を直接並べる（オフセット0から）
        
        def str_to_bytes(s: str, length: int) -> bytes:
            return s.encode('ascii').ljust(length, b'\x00')[:length]
        
        # 256バイトのACKデータを構築
        ack_data = bytearray(256)
        
        # 必須フィールドをACKデータに配置
        # Version (offset 0x0000, 4 bytes)
        struct.pack_into('>I', ack_data, 0x0000, 0x00010200)
        
        # Device Mode (offset 0x0004, 4 bytes)
        struct.pack_into('>I', ack_data, 0x0004, 0x00000000)
        
        # Device MAC Address (offset 0x0008, 6 bytes: High 2 bytes + Low 4 bytes)
        # 仮想MACアドレスを生成（シリアル番号から）
        serial = self.device_info.get('serial', 'MOCK001')
        mac_suffix = hash(serial) & 0xFFFFFFFF
        # MAC High (0x0008, 2 bytes) - 先頭2バイト
        struct.pack_into('>H', ack_data, 0x0008, 0x0200)
        # MAC Low (0x000C, 4 bytes) - 後ろ4バイト
        struct.pack_into('>I', ack_data, 0x000C, mac_suffix)
        
        # Supported IP Configuration (offset 0x0010, 4 bytes)
        struct.pack_into('>I', ack_data, 0x0010, 0x00000007)  # LLA, DHCP, Persistent IP
        
        # Current IP Configuration (offset 0x0014, 4 bytes)
        struct.pack_into('>I', ack_data, 0x0014, 0x00000004)  # Persistent IP
        
        # Current IP Address (offset 0x0024, 4 bytes)
        local_ip = self.device_info.get('local_ip', '192.168.1.100')
        ip_parts = local_ip.split('.')
        if len(ip_parts) == 4:
            ack_data[0x0024:0x0028] = bytes([int(p) for p in ip_parts])
        
        # Current Subnet Mask (offset 0x0034, 4 bytes)
        ack_data[0x0034:0x0038] = bytes([255, 255, 255, 0])
        
        # Current Gateway (offset 0x0044, 4 bytes)
        ack_data[0x0044:0x0048] = bytes([192, 168, 1, 1])
        
        # Manufacturer Name (offset 0x0048, 32 bytes)
        vendor = str_to_bytes(self.device_info.get('vendor', 'MockCam'), 32)
        ack_data[0x0048:0x0068] = vendor
        
        # Model Name (offset 0x0068, 32 bytes)
        model = str_to_bytes(self.device_info.get('model', 'VirtualCam-1'), 32)
        ack_data[0x0068:0x0088] = model
        
        # Device Version (offset 0x0088, 32 bytes)
        version = str_to_bytes('1.0.0', 32)
        ack_data[0x0088:0x00A8] = version
        
        # Manufacturer Info (offset 0x00A8, 48 bytes)
        info = str_to_bytes('Mock GigE Camera', 48)
        ack_data[0x00A8:0x00D8] = info
        
        # Serial Number (offset 0x00D8, 16 bytes)
        serial = str_to_bytes(self.device_info.get('serial', 'MOCK001'), 16)
        ack_data[0x00D8:0x00E8] = serial
        
        # User Defined Name (offset 0x00E8, 16 bytes)
        user_name = str_to_bytes(self.device_info.get('user_name', 'TestCamera'), 16)
        ack_data[0x00E8:0x00F8] = user_name
        
        response = struct.pack('>BBHHH', 0x42, 0x01, GVCPCommand.DISCOVERY_ACK, len(ack_data), packet.request_id)
        
        # デバッグ: ACKデータの内容を表示
        logger.info(f"ACK data: IP={local_ip}, Vendor={self.device_info.get('vendor')}, Model={self.device_info.get('model')}, Serial={self.device_info.get('serial')}")
        logger.debug(f"ACK first 64 bytes: {bytes(ack_data[:64]).hex(' ')}")
        
        return response + bytes(ack_data)
    
    def _handle_readreg(self, packet: GVCPPacket) -> bytes:
        """レジスタ読み取りコマンドを処理"""
        if len(packet.data) < 4:
            return self._error_response(packet, GVCPStatus.INVALID_PARAMETER)
        
        address = struct.unpack('>I', packet.data[:4])[0]
        
        if address in self.registers:
            reg_data = self.registers[address]
            response = struct.pack('>BBHHH', 0x42, 0x01, GVCPCommand.READREG_ACK, 
                                  len(reg_data), packet.request_id)
            return response + reg_data
        else:
            return self._error_response(packet, GVCPStatus.INVALID_ADDRESS)
    
    def _handle_writereg(self, packet: GVCPPacket) -> bytes:
        """レジスタ書き込みコマンドを処理"""
        if len(packet.data) < 8:
            return self._error_response(packet, GVCPStatus.INVALID_PARAMETER)
        
        address = struct.unpack('>I', packet.data[:4])[0]
        value = packet.data[4:]
        
        self.registers[address] = value
        
        response = struct.pack('>BBHHH', 0x42, 0x01, GVCPCommand.WRITEREG_ACK, 
                              4, packet.request_id)
        response += struct.pack('>I', 0)
        return response
    
    def _handle_readmem(self, packet: GVCPPacket) -> bytes:
        """Handle read memory command"""
        if len(packet.data) < 8:
            return self._error_response(packet, GVCPStatus.INVALID_PARAMETER)
        
        address, count = struct.unpack('>II', packet.data[:8])
        
        data = bytes(count)
        response = struct.pack('>HHHI', GVCPCommand.READMEM_ACK, 0x0001, 
                              len(data), packet.request_id)
        return response + data
    
    def _error_response(self, packet: GVCPPacket, status: GVCPStatus) -> bytes:
        """エラー応答を生成"""
        response = struct.pack('>BBHHH', 0x42, 0x01, packet.command | 0x0001, 
                              4, packet.request_id)
        response += struct.pack('>I', status)
        return response


class GVSPServer:
    """GigE Vision Streaming Protocol Server"""
    
    def __init__(self, bind_ip: str = "0.0.0.0", port: int = 50000):
        self.bind_ip = bind_ip
        self.port = port
        self.socket: Optional[socket.socket] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.block_id = 0
        self.packet_id = 0
        self.dest_ip: Optional[str] = None
        self.dest_port: Optional[int] = None
    
    def start(self):
        """Start GVSP server"""
        if self.running:
            return
        
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.bind_ip, self.port))
        
        self.running = True
        print(f"[GVSP] Server started on {self.bind_ip}:{self.port}")
    
    def stop(self):
        """Stop GVSP server"""
        self.running = False
        if self.socket:
            self.socket.close()
        print("[GVSP] Server stopped")
    
    def set_destination(self, ip: str, port: int):
        """Set streaming destination"""
        self.dest_ip = ip
        self.dest_port = port
    
    def send_image(self, image_data: bytes, width: int, height: int, 
                   pixel_format: int = GVSPPixelType.MONO8):
        """Send image via GVSP"""
        if not self.running or not self.dest_ip or not self.dest_port:
            return
        
        self.block_id += 1
        self.packet_id = 0
        
        leader = self._create_leader_packet(width, height, pixel_format, len(image_data))
        self._send_packet(leader)
        
        chunk_size = 1400
        for i in range(0, len(image_data), chunk_size):
            chunk = image_data[i:i+chunk_size]
            payload = self._create_payload_packet(chunk)
            self._send_packet(payload)
        
        trailer = self._create_trailer_packet()
        self._send_packet(trailer)
    
    def _create_leader_packet(self, width: int, height: int, 
                              pixel_format: int, payload_size: int) -> bytes:
        """Create GVSP leader packet"""
        header = struct.pack('>BBHI', 0x01, 0x00, self.block_id & 0xFFFF, 
                            (self.packet_id << 24) | 0x01)
        
        payload_type = struct.pack('>HH', 0x0001, 0)
        timestamp = struct.pack('>Q', int(time.time() * 1e9) & 0xFFFFFFFFFFFFFFFF)
        pixel_format_bytes = struct.pack('>I', pixel_format)
        size_bytes = struct.pack('>II', width, height)
        offset_bytes = struct.pack('>II', 0, 0)
        padding = struct.pack('>HH', 0, 0)
        
        self.packet_id += 1
        return header + payload_type + timestamp + pixel_format_bytes + size_bytes + offset_bytes + padding
    
    def _create_payload_packet(self, data: bytes) -> bytes:
        """Create GVSP payload packet"""
        header = struct.pack('>BBHI', 0x01, 0x00, self.block_id & 0xFFFF,
                            (self.packet_id << 24) | 0x02)
        self.packet_id += 1
        return header + data
    
    def _create_trailer_packet(self) -> bytes:
        """Create GVSP trailer packet"""
        header = struct.pack('>BBHI', 0x01, 0x00, self.block_id & 0xFFFF,
                            (self.packet_id << 24) | 0x03)
        payload_type = struct.pack('>HH', 0x0001, 0)
        size_bytes = struct.pack('>Q', 0)
        self.packet_id += 1
        return header + payload_type + size_bytes
    
    def _send_packet(self, packet: bytes):
        """Send packet to destination"""
        if self.socket and self.dest_ip and self.dest_port:
            try:
                self.socket.sendto(packet, (self.dest_ip, self.dest_port))
            except Exception as e:
                print(f"[GVSP] Send error: {e}")
