"""
モックPLCサーバー
MCプロトコルに対応した三菱PLCシミュレーター
"""
import socket
import struct
import threading
import time
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from mc_protocol import (
    MCProtocol, MCCommand, MCSubCommand, PLCSeries,
    DeviceType, get_error_message
)
from plc_devices import PLCDeviceManager
from ladder_engine import LadderEngine, LadderProgram


class PLCState(Enum):
    """PLC状態"""
    STOP = "STOP"
    RUN = "RUN"
    PAUSE = "PAUSE"
    ERROR = "ERROR"


@dataclass
class PLCInfo:
    """PLC情報"""
    series: PLCSeries
    model: str
    version: str
    
    def get_model_name(self) -> str:
        if self.series == PLCSeries.Q_SERIES:
            return f"Q{self.model}"
        else:
            return f"R{self.model}"


class MockPLCServer:
    """
    モックPLCサーバー
    
    三菱PLCのMCプロトコルをシミュレート
    """
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5000,
        series: PLCSeries = PLCSeries.Q_SERIES
    ):
        self.host = host
        self.port = port
        self.series = series
        
        # PLC情報
        self.info = PLCInfo(
            series=series,
            model="03UD" if series == PLCSeries.Q_SERIES else "04CPU",
            version="1.00"
        )
        
        # PLC状態
        self.state = PLCState.STOP
        
        # デバイス管理
        self.devices = PLCDeviceManager(is_iqr=(series == PLCSeries.IQR_SERIES))
        
        # ラダーエンジン
        self.ladder_engine = LadderEngine(self.devices)
        
        # サーバー
        self._server_socket: Optional[socket.socket] = None
        self._client_socket: Optional[socket.socket] = None
        self._running = False
        self._server_thread: Optional[threading.Thread] = None
        
        # コールバック
        self.on_client_connected: Optional[Callable[[str, int], None]] = None
        self.on_client_disconnected: Optional[Callable[[], None]] = None
        self.on_command_received: Optional[Callable[[str, dict], None]] = None
        self.on_state_changed: Optional[Callable[[PLCState], None]] = None
        self.on_log: Optional[Callable[[str], None]] = None
        
        # 通信設定
        self.response_delay_ms = 0  # レスポンス遅延（テスト用）
        self.error_rate = 0.0  # エラー率（テスト用）
    
    def _log(self, message: str):
        """ログ出力"""
        if self.on_log:
            self.on_log(message)
        else:
            print(f"[MockPLC] {message}")
    
    def start(self) -> bool:
        """サーバーを開始"""
        if self._running:
            return False
        
        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind((self.host, self.port))
            self._server_socket.listen(1)
            self._server_socket.settimeout(1.0)
            
            self._running = True
            self._server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self._server_thread.start()
            
            self._log(f"Server started on {self.host}:{self.port}")
            return True
            
        except Exception as e:
            self._log(f"Server start error: {e}")
            return False
    
    def stop(self):
        """サーバーを停止"""
        self._running = False
        
        # ラダー停止
        self.ladder_engine.stop()
        
        # クライアント切断
        if self._client_socket:
            try:
                self._client_socket.close()
            except:
                pass
            self._client_socket = None
        
        # サーバー停止
        if self._server_socket:
            try:
                self._server_socket.close()
            except:
                pass
            self._server_socket = None
        
        if self._server_thread:
            self._server_thread.join(timeout=2.0)
            self._server_thread = None
        
        self._log("Server stopped")
    
    def _server_loop(self):
        """サーバーループ"""
        while self._running:
            try:
                # クライアント接続待機
                if self._client_socket is None:
                    try:
                        client, addr = self._server_socket.accept()
                        self._client_socket = client
                        self._client_socket.settimeout(0.5)
                        self._log(f"Client connected: {addr}")
                        
                        if self.on_client_connected:
                            self.on_client_connected(addr[0], addr[1])
                    except socket.timeout:
                        continue
                    except Exception as e:
                        if self._running:
                            self._log(f"Accept error: {e}")
                        continue
                
                # データ受信
                try:
                    data = self._client_socket.recv(4096)
                    if not data:
                        self._handle_disconnect()
                        continue
                    
                    # リクエスト処理
                    response = self._handle_request(data)
                    
                    # レスポンス遅延
                    if self.response_delay_ms > 0:
                        time.sleep(self.response_delay_ms / 1000.0)
                    
                    # レスポンス送信
                    if response:
                        self._client_socket.send(response)
                        
                except socket.timeout:
                    continue
                except ConnectionResetError:
                    self._handle_disconnect()
                except Exception as e:
                    if self._running:
                        self._log(f"Communication error: {e}")
                    self._handle_disconnect()
                    
            except Exception as e:
                if self._running:
                    self._log(f"Server loop error: {e}")
    
    def _handle_disconnect(self):
        """切断処理"""
        if self._client_socket:
            try:
                self._client_socket.close()
            except:
                pass
            self._client_socket = None
            self._log("Client disconnected")
            
            if self.on_client_disconnected:
                self.on_client_disconnected()
    
    def _handle_request(self, data: bytes) -> bytes:
        """リクエストを処理"""
        try:
            # リクエスト解析
            request = MCProtocol.parse_request(data)
            
            # コマンド取得
            command = request.get('command', 0)
            sub_command = request.get('sub_command', 0)
            command_data = request.get('command_data', b'')
            
            # コールバック
            if self.on_command_received:
                self.on_command_received(
                    f"CMD:{command:#06x} SUB:{sub_command:#06x}",
                    request
                )
            
            # コマンド処理
            end_code, response_data = self._process_command(
                command, sub_command, command_data
            )
            
            # レスポンス構築
            return MCProtocol.build_response(
                series=self.series,
                end_code=end_code,
                data=response_data,
                network_no=request.get('network_no', 0),
                pc_no=request.get('pc_no', 0xFF),
                serial_no=request.get('serial_no', 0)
            )
            
        except Exception as e:
            self._log(f"Request handling error: {e}")
            return MCProtocol.build_response(
                series=self.series,
                end_code=0x0050  # コマンドエラー
            )
    
    def _process_command(
        self, 
        command: int, 
        sub_command: int, 
        data: bytes
    ) -> tuple:
        """コマンドを処理"""
        
        # 一括読出し
        if command == MCCommand.BATCH_READ.value:
            return self._cmd_batch_read(sub_command, data)
        
        # 一括書込み
        elif command == MCCommand.BATCH_WRITE.value:
            return self._cmd_batch_write(sub_command, data)
        
        # CPU型名読出し
        elif command == MCCommand.CPU_MODEL_READ.value:
            return self._cmd_cpu_model_read()
        
        # リモートRUN
        elif command == MCCommand.REMOTE_RUN.value:
            return self._cmd_remote_run()
        
        # リモートSTOP
        elif command == MCCommand.REMOTE_STOP.value:
            return self._cmd_remote_stop()
        
        # リモートPAUSE
        elif command == MCCommand.REMOTE_PAUSE.value:
            return self._cmd_remote_pause()
        
        # リモートRESET
        elif command == MCCommand.REMOTE_RESET.value:
            return self._cmd_remote_reset()
        
        # 未対応コマンド
        else:
            self._log(f"Unsupported command: {command:#06x}")
            return 0x0050, b''
    
    def _cmd_batch_read(self, sub_command: int, data: bytes) -> tuple:
        """一括読出し"""
        if len(data) < 6:
            return 0xC050, b''
        
        # デバイス解析
        device_addr = struct.unpack('<I', data[0:3] + b'\x00')[0]
        device_code = data[3]
        count = struct.unpack('<H', data[4:6])[0]
        
        # デバイスタイプ取得
        device_type = None
        for dt in DeviceType:
            if dt.device_code == device_code:
                device_type = dt
                break
        
        if device_type is None:
            return 0xC050, b''  # デバイス指定エラー
        
        # ビット読出し
        if sub_command == MCSubCommand.BIT.value:
            values = self.devices.get_bits(device_type, device_addr, count)
            response_data = bytes([0x01 if v else 0x00 for v in values])
        
        # ワード読出し
        else:
            if device_type.is_bit_device:
                # ビットデバイスをワードとして読出し
                word_count = count
                response_data = b''
                for i in range(word_count):
                    word_val = self.devices.get_bit_as_word(device_type, device_addr + i * 16)
                    response_data += struct.pack('<H', word_val)
            else:
                values = self.devices.get_words(device_type, device_addr, count)
                response_data = b''.join(struct.pack('<H', v) for v in values)
        
        return 0x0000, response_data
    
    def _cmd_batch_write(self, sub_command: int, data: bytes) -> tuple:
        """一括書込み"""
        if len(data) < 6:
            return 0xC050, b''
        
        # デバイス解析
        device_addr = struct.unpack('<I', data[0:3] + b'\x00')[0]
        device_code = data[3]
        count = struct.unpack('<H', data[4:6])[0]
        write_data = data[6:]
        
        # デバイスタイプ取得
        device_type = None
        for dt in DeviceType:
            if dt.device_code == device_code:
                device_type = dt
                break
        
        if device_type is None:
            return 0xC050, b''
        
        # ビット書込み
        if sub_command == MCSubCommand.BIT.value:
            values = [bool(b) for b in write_data[:count]]
            if not self.devices.set_bits(device_type, device_addr, values):
                return 0xC051, b''
        
        # ワード書込み
        else:
            if device_type.is_bit_device:
                # ビットデバイスへのワード書込み
                for i in range(count):
                    if len(write_data) >= (i + 1) * 2:
                        word_val = struct.unpack('<H', write_data[i*2:(i+1)*2])[0]
                        self.devices.set_bit_from_word(device_type, device_addr + i * 16, word_val)
            else:
                values = []
                for i in range(count):
                    if len(write_data) >= (i + 1) * 2:
                        values.append(struct.unpack('<H', write_data[i*2:(i+1)*2])[0])
                if not self.devices.set_words(device_type, device_addr, values):
                    return 0xC051, b''
        
        return 0x0000, b''
    
    def _cmd_cpu_model_read(self) -> tuple:
        """CPU型名読出し"""
        model_name = self.info.get_model_name().encode('ascii')
        # 16バイトに調整
        model_name = model_name[:16].ljust(16, b'\x00')
        return 0x0000, model_name
    
    def _cmd_remote_run(self) -> tuple:
        """リモートRUN"""
        self.state = PLCState.RUN
        self.ladder_engine.start()
        self._log("PLC RUN")
        
        if self.on_state_changed:
            self.on_state_changed(self.state)
        
        return 0x0000, b''
    
    def _cmd_remote_stop(self) -> tuple:
        """リモートSTOP"""
        self.state = PLCState.STOP
        self.ladder_engine.stop()
        self._log("PLC STOP")
        
        if self.on_state_changed:
            self.on_state_changed(self.state)
        
        return 0x0000, b''
    
    def _cmd_remote_pause(self) -> tuple:
        """リモートPAUSE"""
        self.state = PLCState.PAUSE
        self.ladder_engine.stop()
        self._log("PLC PAUSE")
        
        if self.on_state_changed:
            self.on_state_changed(self.state)
        
        return 0x0000, b''
    
    def _cmd_remote_reset(self) -> tuple:
        """リモートRESET"""
        self.state = PLCState.STOP
        self.ladder_engine.stop()
        self.ladder_engine.reset_all()
        self.devices.clear_all()
        self._log("PLC RESET")
        
        if self.on_state_changed:
            self.on_state_changed(self.state)
        
        return 0x0000, b''
    
    # === 公開API ===
    
    def set_series(self, series: PLCSeries):
        """シリーズを変更"""
        self.series = series
        self.info.series = series
        self.devices = PLCDeviceManager(is_iqr=(series == PLCSeries.IQR_SERIES))
        self.ladder_engine = LadderEngine(self.devices)
        
        if series == PLCSeries.Q_SERIES:
            self.info.model = "03UD"
        else:
            self.info.model = "04CPU"
    
    def load_ladder_program(self, program: LadderProgram):
        """ラダープログラムをロード"""
        self.ladder_engine.add_program(program)
        self._log(f"Ladder program loaded: {program.name}")
    
    def clear_ladder_programs(self):
        """ラダープログラムをクリア"""
        self.ladder_engine.clear_programs()
        self._log("Ladder programs cleared")
    
    def get_device_value(self, device_code: str, address: int) -> int:
        """デバイス値を取得"""
        device_type = DeviceType.from_code(device_code)
        if device_type is None:
            return 0
        
        if device_type.is_bit_device:
            return 1 if self.devices.get_bit(device_type, address) else 0
        else:
            return self.devices.get_word(device_type, address)
    
    def set_device_value(self, device_code: str, address: int, value: int):
        """デバイス値を設定"""
        device_type = DeviceType.from_code(device_code)
        if device_type is None:
            return
        
        if device_type.is_bit_device:
            self.devices.set_bit(device_type, address, bool(value))
        else:
            self.devices.set_word(device_type, address, value)
    
    @property
    def is_running(self) -> bool:
        """サーバーが実行中か"""
        return self._running
    
    @property
    def is_connected(self) -> bool:
        """クライアントが接続中か"""
        return self._client_socket is not None
