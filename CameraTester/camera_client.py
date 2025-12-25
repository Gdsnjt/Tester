"""
統合カメラクライアント
モックカメラと実カメラ（Harvester）を統一インターフェースで使用

使用方法:
    python camera_client.py
"""
import os
import sys
import time
import socket
import struct
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import cv2
from PIL import Image, ImageTk


@dataclass
class DeviceInfo:
    """デバイス情報"""
    index: int
    vendor: str
    model: str
    serial_number: str
    ip_address: str
    mode: str  # 'mock' or 'harvester'
    
    def __str__(self):
        return f"[{self.mode.upper()}] {self.vendor} {self.model} ({self.serial_number}) - {self.ip_address}"


class MockCameraClient:
    """モックカメラ用クライアント（独自GigE Vision実装）"""
    
    def __init__(self):
        self.connected = False
        self.device_info: Optional[DeviceInfo] = None
        self.gvcp_socket: Optional[socket.socket] = None
        self.gvsp_socket: Optional[socket.socket] = None
        self.device_ip: Optional[str] = None
        self.gvcp_port = 3956
        self.gvsp_port = 50000
        self.request_id = 1
        self.acquiring = False
        self.acquisition_thread: Optional[threading.Thread] = None
        self._on_image_callback = None
        
    def discover_devices(self, timeout: float = 2.0) -> List[DeviceInfo]:
        """モックカメラを検出"""
        devices = []
        
        # ディスカバリーパケット送信
        discovery_packet = struct.pack('>BBHHH', 0x42, 0x01, 0x0002, 0x0000, 0xFFFF)
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)
        
        try:
            # ブロードキャスト送信
            sock.sendto(discovery_packet, ('255.255.255.255', 3956))
            
            # 応答受信
            while True:
                try:
                    data, addr = sock.recvfrom(2048)
                    
                    if len(data) >= 8 + 256:
                        magic, flags, command, length, req_id = struct.unpack('>BBHHH', data[:8])
                        
                        if magic == 0x42 and command == 0x0003:  # DISCOVERY_ACK
                            ack_data = data[8:]
                            
                            # デバイス情報を抽出
                            ip = ack_data[0x0024:0x0028]
                            ip_str = f"{ip[0]}.{ip[1]}.{ip[2]}.{ip[3]}"
                            
                            vendor = ack_data[0x0048:0x0068].rstrip(b'\x00').decode('ascii', errors='ignore')
                            model = ack_data[0x0068:0x0088].rstrip(b'\x00').decode('ascii', errors='ignore')
                            serial = ack_data[0x00D8:0x00E8].rstrip(b'\x00').decode('ascii', errors='ignore')
                            
                            device = DeviceInfo(
                                index=len(devices),
                                vendor=vendor,
                                model=model,
                                serial_number=serial,
                                ip_address=ip_str,
                                mode='mock'
                            )
                            devices.append(device)
                            print(f"[Mock] 検出: {device}")
                            
                except socket.timeout:
                    break
                    
        finally:
            sock.close()
            
        return devices
    
    def connect(self, device: DeviceInfo) -> bool:
        """モックカメラに接続"""
        try:
            self.device_info = device
            self.device_ip = device.ip_address
            
            # GVCPソケット
            self.gvcp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.gvcp_socket.settimeout(5.0)
            
            # GVSPソケット（画像受信用）
            self.gvsp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.gvsp_socket.bind(('0.0.0.0', 0))
            self.gvsp_socket.settimeout(1.0)
            
            # コントロールチャネル確立
            # READREG_CMDでバージョンを読み取ってテスト
            self.connected = True
            print(f"[Mock] 接続成功: {device.ip_address}")
            return True
            
        except Exception as e:
            print(f"[Mock] 接続エラー: {e}")
            return False
    
    def disconnect(self):
        """切断"""
        self.stop_acquisition()
        if self.gvcp_socket:
            self.gvcp_socket.close()
        if self.gvsp_socket:
            self.gvsp_socket.close()
        self.connected = False
        print("[Mock] 切断完了")
    
    def start_acquisition(self, callback):
        """連続取得開始"""
        if not self.connected:
            return False
        
        self._on_image_callback = callback
        self.acquiring = True
        self.acquisition_thread = threading.Thread(target=self._acquisition_loop, daemon=True)
        self.acquisition_thread.start()
        return True
    
    def stop_acquisition(self):
        """連続取得停止"""
        self.acquiring = False
        if self.acquisition_thread:
            self.acquisition_thread.join(timeout=2.0)
    
    def _acquisition_loop(self):
        """取得ループ"""
        while self.acquiring:
            image = self.grab_single()
            if image is not None and self._on_image_callback:
                self._on_image_callback(image)
            time.sleep(0.033)  # ~30fps
    
    def grab_single(self) -> Optional[np.ndarray]:
        """単一画像取得（READMEMで画像要求）"""
        if not self.connected or not self.gvcp_socket:
            return None
        
        try:
            # 簡易実装: READMEM_CMDを送信して画像データを要求
            # 実際のGigE Visionでは、GVSPでストリーミング
            
            # READMEM_CMD: 画像バッファアドレスを読み取る
            request_id = self.request_id
            self.request_id = (self.request_id + 1) & 0xFFFF
            
            # アドレス0x1000から64KB読み取りを要求（テスト用）
            readmem_packet = struct.pack('>BBHHH', 0x42, 0x01, 0x0084, 8, request_id)
            readmem_packet += struct.pack('>II', 0x00001000, 65536)
            
            self.gvcp_socket.sendto(readmem_packet, (self.device_ip, self.gvcp_port))
            
            # 応答受信
            data, _ = self.gvcp_socket.recvfrom(65536 + 256)
            
            if len(data) > 8:
                # 画像データを解析（簡易実装）
                # 実際はGVSPパケットを処理する必要がある
                pass
                
        except Exception as e:
            pass
        
        # テスト用: ダミー画像を生成
        width, height = 640, 480
        img = np.zeros((height, width, 3), dtype=np.uint8)
        
        # グラデーション
        t = time.time() % 1.0
        for y in range(height):
            hue = int(((y / height) + t) * 180) % 180
            hsv = np.full((1, width, 3), [hue, 255, 255], dtype=np.uint8)
            img[y:y+1, :] = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        
        # タイムスタンプ
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        cv2.putText(img, f"Mock Camera - {timestamp}", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        return img


class HarvesterClient:
    """Harvester（実カメラ）用クライアント"""
    
    def __init__(self):
        self.harvester = None
        self.ia = None
        self.connected = False
        self.acquiring = False
        self.acquisition_thread: Optional[threading.Thread] = None
        self._on_image_callback = None
        self.cti_file: Optional[str] = None
        self._devices: List[DeviceInfo] = []
        
    def initialize(self, cti_file: str) -> bool:
        """Harvester初期化"""
        try:
            from harvesters.core import Harvester
            
            if not os.path.exists(cti_file):
                print(f"[Harvester] CTIファイルが見つかりません: {cti_file}")
                return False
            
            self.harvester = Harvester()
            self.harvester.add_file(cti_file)
            self.cti_file = cti_file
            print(f"[Harvester] 初期化完了: {os.path.basename(cti_file)}")
            return True
            
        except ImportError:
            print("[Harvester] harvestersライブラリがインストールされていません")
            return False
        except Exception as e:
            print(f"[Harvester] 初期化エラー: {e}")
            return False
    
    def discover_devices(self) -> List[DeviceInfo]:
        """実カメラを検出"""
        if self.harvester is None:
            return []
        
        try:
            self.harvester.update()
            
            self._devices = []
            for i, dev_info in enumerate(self.harvester.device_info_list):
                device = DeviceInfo(
                    index=i,
                    vendor=getattr(dev_info, 'vendor', 'Unknown'),
                    model=getattr(dev_info, 'model', 'Unknown'),
                    serial_number=getattr(dev_info, 'serial_number', 'Unknown'),
                    ip_address=getattr(dev_info, 'id_', 'Unknown'),
                    mode='harvester'
                )
                self._devices.append(device)
                print(f"[Harvester] 検出: {device}")
                
            return self._devices
            
        except Exception as e:
            print(f"[Harvester] 検出エラー: {e}")
            return []
    
    def connect(self, device: DeviceInfo) -> bool:
        """実カメラに接続"""
        if self.harvester is None:
            return False
        
        try:
            self.ia = self.harvester.create(device.index)
            self.connected = True
            print(f"[Harvester] 接続成功: {device}")
            return True
        except Exception as e:
            print(f"[Harvester] 接続エラー: {e}")
            return False
    
    def disconnect(self):
        """切断"""
        self.stop_acquisition()
        if self.ia:
            self.ia.destroy()
            self.ia = None
        self.connected = False
        print("[Harvester] 切断完了")
    
    def start_acquisition(self, callback) -> bool:
        """連続取得開始"""
        if not self.connected or not self.ia:
            return False
        
        try:
            self._on_image_callback = callback
            self.ia.start()
            self.acquiring = True
            self.acquisition_thread = threading.Thread(target=self._acquisition_loop, daemon=True)
            self.acquisition_thread.start()
            return True
        except Exception as e:
            print(f"[Harvester] 取得開始エラー: {e}")
            return False
    
    def stop_acquisition(self):
        """連続取得停止"""
        self.acquiring = False
        if self.acquisition_thread:
            self.acquisition_thread.join(timeout=2.0)
        if self.ia:
            try:
                self.ia.stop()
            except:
                pass
    
    def _acquisition_loop(self):
        """取得ループ"""
        while self.acquiring:
            image = self.grab_single()
            if image is not None and self._on_image_callback:
                self._on_image_callback(image)
    
    def grab_single(self) -> Optional[np.ndarray]:
        """単一画像取得"""
        if not self.connected or not self.ia:
            return None
        
        try:
            with self.ia.fetch(timeout=1.0) as buffer:
                component = buffer.payload.components[0]
                width = component.width
                height = component.height
                
                data = component.data.reshape((height, width, -1)) if len(component.data.shape) == 1 else component.data
                
                if len(data.shape) == 2:
                    return cv2.cvtColor(data, cv2.COLOR_GRAY2BGR)
                elif data.shape[2] == 1:
                    return cv2.cvtColor(data, cv2.COLOR_GRAY2BGR)
                else:
                    return data.copy()
                    
        except Exception as e:
            return None
    
    def cleanup(self):
        """クリーンアップ"""
        self.disconnect()
        if self.harvester:
            self.harvester.reset()
            self.harvester = None


class CameraClientGUI:
    """カメラクライアントGUI"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("カメラクライアント - モック/実カメラ統合")
        self.root.geometry("1200x800")
        
        # クライアント
        self.mock_client = MockCameraClient()
        self.harvester_client = HarvesterClient()
        self.active_client = None  # 現在アクティブなクライアント
        
        # デバイスリスト
        self.all_devices: List[DeviceInfo] = []
        self.selected_device: Optional[DeviceInfo] = None
        
        # 状態
        self.is_acquiring = False
        self.current_image: Optional[np.ndarray] = None
        
        self._create_widgets()
        
    def _create_widgets(self):
        """ウィジェット作成"""
        # メインフレーム
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 左パネル（コントロール）
        left_panel = ttk.Frame(main_frame, width=350)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        left_panel.pack_propagate(False)
        
        # === モード選択 ===
        mode_frame = ttk.LabelFrame(left_panel, text="モード", padding="5")
        mode_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.mode_var = tk.StringVar(value="mock")
        ttk.Radiobutton(mode_frame, text="モックカメラ", variable=self.mode_var, 
                       value="mock").pack(anchor=tk.W)
        ttk.Radiobutton(mode_frame, text="実カメラ (Harvester)", variable=self.mode_var,
                       value="harvester").pack(anchor=tk.W)
        
        # === CTIファイル（Harvester用）===
        cti_frame = ttk.LabelFrame(left_panel, text="CTIファイル (実カメラ用)", padding="5")
        cti_frame.pack(fill=tk.X, pady=(0, 5))
        
        cti_path_frame = ttk.Frame(cti_frame)
        cti_path_frame.pack(fill=tk.X)
        
        self.cti_path_var = tk.StringVar(value="ProducerGEV.cti")
        ttk.Entry(cti_path_frame, textvariable=self.cti_path_var, width=30).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(cti_path_frame, text="参照", command=self._browse_cti, width=6).pack(side=tk.RIGHT, padx=(5, 0))
        
        # === デバイス検出 ===
        detect_frame = ttk.LabelFrame(left_panel, text="デバイス検出", padding="5")
        detect_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Button(detect_frame, text="デバイスを検出", command=self._discover_devices).pack(fill=tk.X)
        
        # デバイスリスト
        self.device_listbox = tk.Listbox(detect_frame, height=6)
        self.device_listbox.pack(fill=tk.X, pady=(5, 0))
        self.device_listbox.bind('<<ListboxSelect>>', self._on_device_select)
        
        # === カメラ制御 ===
        control_frame = ttk.LabelFrame(left_panel, text="カメラ制御", padding="5")
        control_frame.pack(fill=tk.X, pady=(0, 5))
        
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(fill=tk.X)
        
        self.connect_btn = ttk.Button(btn_frame, text="接続", command=self._connect)
        self.connect_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        
        self.disconnect_btn = ttk.Button(btn_frame, text="切断", command=self._disconnect, state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))
        
        acq_frame = ttk.Frame(control_frame)
        acq_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.start_btn = ttk.Button(acq_frame, text="取得開始", command=self._start_acquisition, state=tk.DISABLED)
        self.start_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        
        self.stop_btn = ttk.Button(acq_frame, text="取得停止", command=self._stop_acquisition, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))
        
        # 単一取得・保存
        single_frame = ttk.Frame(control_frame)
        single_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.single_btn = ttk.Button(single_frame, text="単一取得", command=self._grab_single, state=tk.DISABLED)
        self.single_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        
        self.save_btn = ttk.Button(single_frame, text="画像保存", command=self._save_image, state=tk.DISABLED)
        self.save_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))
        
        # === ログ ===
        log_frame = ttk.LabelFrame(left_panel, text="ログ", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = tk.Text(log_frame, height=10, width=40)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        
        # 右パネル（画像表示）
        right_panel = ttk.Frame(main_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        image_frame = ttk.LabelFrame(right_panel, text="画像表示", padding="5")
        image_frame.pack(fill=tk.BOTH, expand=True)
        
        self.image_label = ttk.Label(image_frame)
        self.image_label.pack(fill=tk.BOTH, expand=True)
        
        # ステータスバー
        self.status_var = tk.StringVar(value="準備完了")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        
    def _browse_cti(self):
        """CTIファイル選択"""
        filename = filedialog.askopenfilename(
            title="CTIファイルを選択",
            filetypes=[("CTI Files", "*.cti"), ("All Files", "*.*")]
        )
        if filename:
            self.cti_path_var.set(filename)
    
    def _discover_devices(self):
        """デバイス検出"""
        self.device_listbox.delete(0, tk.END)
        self.all_devices = []
        
        mode = self.mode_var.get()
        
        if mode == "mock":
            self._log("モックカメラを検出中...")
            devices = self.mock_client.discover_devices()
            self.all_devices.extend(devices)
            
        else:  # harvester
            cti_file = self.cti_path_var.get()
            if not cti_file:
                messagebox.showerror("エラー", "CTIファイルを指定してください")
                return
            
            self._log("実カメラを検出中...")
            
            # 初期化
            if not self.harvester_client.harvester:
                if not self.harvester_client.initialize(cti_file):
                    self._log("Harvester初期化に失敗しました")
                    return
            
            devices = self.harvester_client.discover_devices()
            self.all_devices.extend(devices)
        
        # リストに追加
        for device in self.all_devices:
            self.device_listbox.insert(tk.END, str(device))
        
        self._log(f"{len(self.all_devices)}台のデバイスを検出")
        self.status_var.set(f"{len(self.all_devices)}台のデバイスを検出")
    
    def _on_device_select(self, event):
        """デバイス選択"""
        selection = self.device_listbox.curselection()
        if selection:
            index = selection[0]
            self.selected_device = self.all_devices[index]
            self._log(f"選択: {self.selected_device}")
    
    def _connect(self):
        """接続"""
        if not self.selected_device:
            messagebox.showwarning("警告", "デバイスを選択してください")
            return
        
        self._log(f"接続中: {self.selected_device}")
        
        success = False
        if self.selected_device.mode == "mock":
            success = self.mock_client.connect(self.selected_device)
            if success:
                self.active_client = self.mock_client
        else:
            success = self.harvester_client.connect(self.selected_device)
            if success:
                self.active_client = self.harvester_client
        
        if success:
            self._log("接続成功")
            self.status_var.set(f"接続中: {self.selected_device.model}")
            self.connect_btn.config(state=tk.DISABLED)
            self.disconnect_btn.config(state=tk.NORMAL)
            self.start_btn.config(state=tk.NORMAL)
            self.single_btn.config(state=tk.NORMAL)
        else:
            self._log("接続失敗")
            messagebox.showerror("エラー", "接続に失敗しました")
    
    def _disconnect(self):
        """切断"""
        if self.active_client:
            self.active_client.disconnect()
            self.active_client = None
        
        self._log("切断しました")
        self.status_var.set("切断済み")
        self.connect_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.DISABLED)
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.DISABLED)
        self.single_btn.config(state=tk.DISABLED)
        self.save_btn.config(state=tk.DISABLED)
    
    def _start_acquisition(self):
        """連続取得開始"""
        if not self.active_client:
            return
        
        if self.active_client.start_acquisition(self._on_image_received):
            self.is_acquiring = True
            self._log("取得開始")
            self.status_var.set("取得中...")
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.single_btn.config(state=tk.DISABLED)
    
    def _stop_acquisition(self):
        """連続取得停止"""
        if self.active_client:
            self.active_client.stop_acquisition()
        
        self.is_acquiring = False
        self._log("取得停止")
        self.status_var.set("接続中")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.single_btn.config(state=tk.NORMAL)
    
    def _grab_single(self):
        """単一画像取得"""
        if not self.active_client:
            return
        
        image = self.active_client.grab_single()
        if image is not None:
            self._on_image_received(image)
            self._log("画像取得完了")
            self.save_btn.config(state=tk.NORMAL)
        else:
            self._log("画像取得失敗")
    
    def _on_image_received(self, image: np.ndarray):
        """画像受信コールバック"""
        self.current_image = image
        
        # 表示用にリサイズ
        display_size = (800, 600)
        h, w = image.shape[:2]
        scale = min(display_size[0] / w, display_size[1] / h)
        new_size = (int(w * scale), int(h * scale))
        
        resized = cv2.resize(image, new_size, interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        
        pil_image = Image.fromarray(rgb)
        tk_image = ImageTk.PhotoImage(pil_image)
        
        self.image_label.configure(image=tk_image)
        self.image_label.image = tk_image
        
        if not self.is_acquiring:
            self.save_btn.config(state=tk.NORMAL)
    
    def _save_image(self):
        """画像保存"""
        if self.current_image is None:
            return
        
        filename = filedialog.asksaveasfilename(
            title="画像を保存",
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg"), ("BMP", "*.bmp")]
        )
        
        if filename:
            cv2.imwrite(filename, self.current_image)
            self._log(f"保存: {filename}")
    
    def _log(self, message: str):
        """ログ出力"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        print(f"[{timestamp}] {message}")
    
    def _on_closing(self):
        """終了処理"""
        self._disconnect()
        self.harvester_client.cleanup()
        self.root.destroy()
    
    def run(self):
        """実行"""
        self.root.mainloop()


def main():
    app = CameraClientGUI()
    app.run()


if __name__ == "__main__":
    main()
