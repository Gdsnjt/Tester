"""
PLCテスターGUI
三菱PLCモックサーバーとクライアントのテストツール
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import time
from datetime import datetime
from typing import Optional

from mc_protocol import PLCSeries, DeviceType
from mock_plc_server import MockPLCServer, PLCState
from plc_client import PLCClient, ConnectionConfig, PLCClientError
from ladder_engine import (
    LadderProgram, LadderEngine,
    create_sample_program_1,
    create_sample_program_2,
    create_sample_program_3,
    create_sample_program_4,
    create_sample_program_5
)


class PLCTesterGUI:
    """PLCテスターGUIアプリケーション"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("三菱PLC テスター")
        self.root.geometry("1200x900")
        
        # サーバー・クライアント
        self.server: Optional[MockPLCServer] = None
        self.client: Optional[PLCClient] = None
        
        # 設定
        self.host = "127.0.0.1"
        self.port = 5000
        self.series = PLCSeries.Q_SERIES
        
        # モニタリング
        self.monitor_running = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        # UI作成
        self._create_widgets()
        
        # ウィンドウを閉じる時の処理
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
    
    def _create_widgets(self):
        """UIウィジェットを作成"""
        # メインコンテナ
        main_container = ttk.Frame(self.root, padding="5")
        main_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_container.columnconfigure(1, weight=1)
        main_container.rowconfigure(2, weight=1)
        
        # === 上部: 設定 ===
        self._create_config_section(main_container)
        
        # === 左側: サーバー ===
        self._create_server_section(main_container)
        
        # === 中央: クライアント ===
        self._create_client_section(main_container)
        
        # === 右側: デバイスモニタ ===
        self._create_monitor_section(main_container)
        
        # === 下部: ログ ===
        self._create_log_section(main_container)
    
    def _create_config_section(self, parent):
        """設定セクション"""
        config_frame = ttk.LabelFrame(parent, text="接続設定", padding="10")
        config_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # ホスト
        ttk.Label(config_frame, text="ホスト:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.host_var = tk.StringVar(value=self.host)
        ttk.Entry(config_frame, textvariable=self.host_var, width=15).grid(row=0, column=1, padx=5)
        
        # ポート
        ttk.Label(config_frame, text="ポート:").grid(row=0, column=2, sticky=tk.W, padx=5)
        self.port_var = tk.StringVar(value=str(self.port))
        ttk.Entry(config_frame, textvariable=self.port_var, width=8).grid(row=0, column=3, padx=5)
        
        # シリーズ
        ttk.Label(config_frame, text="シリーズ:").grid(row=0, column=4, sticky=tk.W, padx=5)
        self.series_var = tk.StringVar(value="Q")
        series_combo = ttk.Combobox(config_frame, textvariable=self.series_var,
                                    values=["Q", "iQ-R"], state="readonly", width=10)
        series_combo.grid(row=0, column=5, padx=5)
        series_combo.bind("<<ComboboxSelected>>", self._on_series_changed)
        
        # ステータス
        self.status_var = tk.StringVar(value="準備完了")
        ttk.Label(config_frame, textvariable=self.status_var, 
                 foreground="blue").grid(row=0, column=6, padx=20)
    
    def _create_server_section(self, parent):
        """サーバーセクション"""
        server_frame = ttk.LabelFrame(parent, text="モックPLCサーバー", padding="10")
        server_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5), pady=5)
        
        # サーバー制御
        ctrl_frame = ttk.Frame(server_frame)
        ctrl_frame.grid(row=0, column=0, columnspan=2, pady=5)
        
        self.server_start_btn = ttk.Button(ctrl_frame, text="サーバー起動", 
                                           command=self._start_server)
        self.server_start_btn.grid(row=0, column=0, padx=5)
        
        self.server_stop_btn = ttk.Button(ctrl_frame, text="サーバー停止", 
                                          command=self._stop_server, state=tk.DISABLED)
        self.server_stop_btn.grid(row=0, column=1, padx=5)
        
        # サーバーステータス
        status_frame = ttk.Frame(server_frame)
        status_frame.grid(row=1, column=0, columnspan=2, pady=5)
        
        ttk.Label(status_frame, text="状態:").grid(row=0, column=0, sticky=tk.W)
        self.server_status_label = ttk.Label(status_frame, text="停止", foreground="red")
        self.server_status_label.grid(row=0, column=1, padx=10)
        
        ttk.Label(status_frame, text="PLC:").grid(row=0, column=2, sticky=tk.W, padx=(20, 0))
        self.plc_state_label = ttk.Label(status_frame, text="-")
        self.plc_state_label.grid(row=0, column=3, padx=10)
        
        # ラダープログラム
        ttk.Separator(server_frame, orient=tk.HORIZONTAL).grid(
            row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)
        
        ttk.Label(server_frame, text="ラダープログラム:").grid(row=3, column=0, sticky=tk.W)
        
        self.ladder_var = tk.StringVar(value="自己保持回路")
        ladder_combo = ttk.Combobox(server_frame, textvariable=self.ladder_var,
                                    values=["自己保持回路", "タイマ回路", "カウンタ回路", 
                                           "データ演算", "複雑条件"],
                                    state="readonly", width=15)
        ladder_combo.grid(row=3, column=1, padx=5)
        
        self.load_ladder_btn = ttk.Button(server_frame, text="ロード", 
                                          command=self._load_ladder, state=tk.DISABLED)
        self.load_ladder_btn.grid(row=4, column=0, pady=5)
        
        self.clear_ladder_btn = ttk.Button(server_frame, text="クリア", 
                                           command=self._clear_ladder, state=tk.DISABLED)
        self.clear_ladder_btn.grid(row=4, column=1, pady=5)
        
        # デバイス直接設定
        ttk.Separator(server_frame, orient=tk.HORIZONTAL).grid(
            row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)
        
        ttk.Label(server_frame, text="デバイス設定:").grid(row=6, column=0, columnspan=2, sticky=tk.W)
        
        device_frame = ttk.Frame(server_frame)
        device_frame.grid(row=7, column=0, columnspan=2, pady=5)
        
        self.server_device_var = tk.StringVar(value="X0")
        ttk.Entry(device_frame, textvariable=self.server_device_var, width=8).grid(row=0, column=0, padx=2)
        
        self.server_value_var = tk.StringVar(value="1")
        ttk.Entry(device_frame, textvariable=self.server_value_var, width=8).grid(row=0, column=1, padx=2)
        
        self.server_set_btn = ttk.Button(device_frame, text="設定", 
                                         command=self._server_set_device, state=tk.DISABLED)
        self.server_set_btn.grid(row=0, column=2, padx=2)
    
    def _create_client_section(self, parent):
        """クライアントセクション"""
        client_frame = ttk.LabelFrame(parent, text="PLCクライアント", padding="10")
        client_frame.grid(row=1, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        
        # 接続制御
        conn_frame = ttk.Frame(client_frame)
        conn_frame.grid(row=0, column=0, columnspan=2, pady=5)
        
        self.connect_btn = ttk.Button(conn_frame, text="接続", command=self._connect)
        self.connect_btn.grid(row=0, column=0, padx=5)
        
        self.disconnect_btn = ttk.Button(conn_frame, text="切断", 
                                         command=self._disconnect, state=tk.DISABLED)
        self.disconnect_btn.grid(row=0, column=1, padx=5)
        
        # 接続ステータス
        self.client_status_label = ttk.Label(client_frame, text="未接続", foreground="red")
        self.client_status_label.grid(row=1, column=0, columnspan=2, pady=5)
        
        # CPU情報読出し
        self.read_cpu_btn = ttk.Button(client_frame, text="CPU型名読出し", 
                                       command=self._read_cpu_model, state=tk.DISABLED)
        self.read_cpu_btn.grid(row=2, column=0, columnspan=2, pady=5)
        
        # リモート制御
        ttk.Separator(client_frame, orient=tk.HORIZONTAL).grid(
            row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)
        
        ttk.Label(client_frame, text="リモート制御:").grid(row=4, column=0, columnspan=2, sticky=tk.W)
        
        remote_frame = ttk.Frame(client_frame)
        remote_frame.grid(row=5, column=0, columnspan=2, pady=5)
        
        self.run_btn = ttk.Button(remote_frame, text="RUN", command=self._remote_run, 
                                  state=tk.DISABLED, width=8)
        self.run_btn.grid(row=0, column=0, padx=2)
        
        self.stop_btn = ttk.Button(remote_frame, text="STOP", command=self._remote_stop, 
                                   state=tk.DISABLED, width=8)
        self.stop_btn.grid(row=0, column=1, padx=2)
        
        self.reset_btn = ttk.Button(remote_frame, text="RESET", command=self._remote_reset, 
                                    state=tk.DISABLED, width=8)
        self.reset_btn.grid(row=0, column=2, padx=2)
        
        # デバイス読み書き
        ttk.Separator(client_frame, orient=tk.HORIZONTAL).grid(
            row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)
        
        ttk.Label(client_frame, text="デバイス操作:").grid(row=7, column=0, columnspan=2, sticky=tk.W)
        
        # デバイス入力
        device_frame = ttk.Frame(client_frame)
        device_frame.grid(row=8, column=0, columnspan=2, pady=5)
        
        ttk.Label(device_frame, text="デバイス:").grid(row=0, column=0)
        self.device_var = tk.StringVar(value="D0")
        ttk.Entry(device_frame, textvariable=self.device_var, width=10).grid(row=0, column=1, padx=5)
        
        ttk.Label(device_frame, text="点数:").grid(row=0, column=2)
        self.count_var = tk.StringVar(value="1")
        ttk.Entry(device_frame, textvariable=self.count_var, width=5).grid(row=0, column=3, padx=5)
        
        # 読み出しボタン
        read_frame = ttk.Frame(client_frame)
        read_frame.grid(row=9, column=0, columnspan=2, pady=5)
        
        self.read_word_btn = ttk.Button(read_frame, text="ワード読出し", 
                                        command=self._read_words, state=tk.DISABLED)
        self.read_word_btn.grid(row=0, column=0, padx=2)
        
        self.read_bit_btn = ttk.Button(read_frame, text="ビット読出し", 
                                       command=self._read_bits, state=tk.DISABLED)
        self.read_bit_btn.grid(row=0, column=1, padx=2)
        
        # 書き込み
        write_frame = ttk.Frame(client_frame)
        write_frame.grid(row=10, column=0, columnspan=2, pady=5)
        
        ttk.Label(write_frame, text="値:").grid(row=0, column=0)
        self.value_var = tk.StringVar(value="0")
        ttk.Entry(write_frame, textvariable=self.value_var, width=10).grid(row=0, column=1, padx=5)
        
        self.write_word_btn = ttk.Button(write_frame, text="ワード書込み", 
                                         command=self._write_word, state=tk.DISABLED)
        self.write_word_btn.grid(row=0, column=2, padx=2)
        
        self.write_bit_btn = ttk.Button(write_frame, text="ビット書込み", 
                                        command=self._write_bit, state=tk.DISABLED)
        self.write_bit_btn.grid(row=0, column=3, padx=2)
        
        # 結果表示
        ttk.Label(client_frame, text="結果:").grid(row=11, column=0, sticky=tk.W, pady=(10, 0))
        self.result_var = tk.StringVar(value="-")
        result_label = ttk.Label(client_frame, textvariable=self.result_var,
                                 wraplength=300, justify=tk.LEFT)
        result_label.grid(row=12, column=0, columnspan=2, sticky=tk.W)
    
    def _create_monitor_section(self, parent):
        """モニターセクション"""
        monitor_frame = ttk.LabelFrame(parent, text="デバイスモニタ", padding="10")
        monitor_frame.grid(row=1, column=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 0), pady=5)
        
        # モニタ制御
        ctrl_frame = ttk.Frame(monitor_frame)
        ctrl_frame.grid(row=0, column=0, columnspan=2, pady=5)
        
        self.monitor_start_btn = ttk.Button(ctrl_frame, text="モニタ開始", 
                                            command=self._start_monitor, state=tk.DISABLED)
        self.monitor_start_btn.grid(row=0, column=0, padx=5)
        
        self.monitor_stop_btn = ttk.Button(ctrl_frame, text="モニタ停止", 
                                           command=self._stop_monitor, state=tk.DISABLED)
        self.monitor_stop_btn.grid(row=0, column=1, padx=5)
        
        # モニタ設定
        settings_frame = ttk.Frame(monitor_frame)
        settings_frame.grid(row=1, column=0, columnspan=2, pady=5)
        
        ttk.Label(settings_frame, text="間隔(ms):").grid(row=0, column=0)
        self.monitor_interval_var = tk.StringVar(value="500")
        ttk.Entry(settings_frame, textvariable=self.monitor_interval_var, width=6).grid(row=0, column=1, padx=5)
        
        # モニタ対象デバイス
        ttk.Label(monitor_frame, text="モニタ対象 (カンマ区切り):").grid(row=2, column=0, columnspan=2, sticky=tk.W)
        self.monitor_devices_var = tk.StringVar(value="X0,X1,Y0,M0,D0,D1,D2")
        ttk.Entry(monitor_frame, textvariable=self.monitor_devices_var, width=30).grid(row=3, column=0, columnspan=2, pady=5)
        
        # モニタ表示
        self.monitor_text = scrolledtext.ScrolledText(monitor_frame, width=30, height=15,
                                                       font=('Consolas', 10))
        self.monitor_text.grid(row=4, column=0, columnspan=2, pady=5)
    
    def _create_log_section(self, parent):
        """ログセクション"""
        log_frame = ttk.LabelFrame(parent, text="ログ", padding="5")
        log_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, font=('Consolas', 9))
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # クリアボタン
        ttk.Button(log_frame, text="ログクリア", command=self._clear_log).grid(row=1, column=0, sticky=tk.E, pady=5)
    
    def _log(self, message: str):
        """ログを追加"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
    
    def _clear_log(self):
        """ログをクリア"""
        self.log_text.delete(1.0, tk.END)
    
    def _update_status(self, message: str):
        """ステータスを更新"""
        self.status_var.set(message)
    
    # === 設定変更 ===
    
    def _on_series_changed(self, event):
        """シリーズ変更時"""
        series_str = self.series_var.get()
        self.series = PLCSeries.Q_SERIES if series_str == "Q" else PLCSeries.IQR_SERIES
        self._log(f"シリーズ変更: {series_str}")
    
    # === サーバー制御 ===
    
    def _start_server(self):
        """サーバーを起動"""
        try:
            host = self.host_var.get()
            port = int(self.port_var.get())
            
            self.server = MockPLCServer(host, port, self.series)
            self.server.on_log = self._log
            self.server.on_client_connected = self._on_server_client_connected
            self.server.on_client_disconnected = self._on_server_client_disconnected
            self.server.on_state_changed = self._on_plc_state_changed
            
            if self.server.start():
                self.server_start_btn['state'] = tk.DISABLED
                self.server_stop_btn['state'] = tk.NORMAL
                self.load_ladder_btn['state'] = tk.NORMAL
                self.clear_ladder_btn['state'] = tk.NORMAL
                self.server_set_btn['state'] = tk.NORMAL
                
                self.server_status_label.config(text="起動中", foreground="green")
                self.plc_state_label.config(text="STOP")
                
                self._log(f"サーバー起動: {host}:{port}")
            else:
                messagebox.showerror("エラー", "サーバー起動に失敗しました")
                
        except Exception as e:
            messagebox.showerror("エラー", f"サーバー起動エラー: {e}")
    
    def _stop_server(self):
        """サーバーを停止"""
        if self.server:
            # モニタ停止
            self._stop_monitor()
            
            self.server.stop()
            self.server = None
            
            self.server_start_btn['state'] = tk.NORMAL
            self.server_stop_btn['state'] = tk.DISABLED
            self.load_ladder_btn['state'] = tk.DISABLED
            self.clear_ladder_btn['state'] = tk.DISABLED
            self.server_set_btn['state'] = tk.DISABLED
            
            self.server_status_label.config(text="停止", foreground="red")
            self.plc_state_label.config(text="-")
            
            self._log("サーバー停止")
    
    def _on_server_client_connected(self, host: str, port: int):
        """クライアント接続時"""
        self.root.after(0, lambda: self._log(f"クライアント接続: {host}:{port}"))
    
    def _on_server_client_disconnected(self):
        """クライアント切断時"""
        self.root.after(0, lambda: self._log("クライアント切断"))
    
    def _on_plc_state_changed(self, state: PLCState):
        """PLC状態変更時"""
        self.root.after(0, lambda: self.plc_state_label.config(text=state.value))
    
    def _load_ladder(self):
        """ラダープログラムをロード"""
        if not self.server:
            return
        
        program_name = self.ladder_var.get()
        program = None
        
        if program_name == "自己保持回路":
            program = create_sample_program_1()
        elif program_name == "タイマ回路":
            program = create_sample_program_2()
        elif program_name == "カウンタ回路":
            program = create_sample_program_3()
        elif program_name == "データ演算":
            program = create_sample_program_4()
        elif program_name == "複雑条件":
            program = create_sample_program_5()
        
        if program:
            self.server.load_ladder_program(program)
            self._log(f"ラダープログラムロード: {program_name}")
    
    def _clear_ladder(self):
        """ラダープログラムをクリア"""
        if self.server:
            self.server.clear_ladder_programs()
            self._log("ラダープログラムクリア")
    
    def _server_set_device(self):
        """サーバー側でデバイスを設定"""
        if not self.server:
            return
        
        try:
            device_str = self.server_device_var.get().upper()
            value = int(self.server_value_var.get())
            
            # デバイス解析
            device_type = None
            address = 0
            
            for dt in DeviceType:
                if device_str.startswith(dt.code):
                    device_type = dt
                    addr_str = device_str[len(dt.code):]
                    base = 16 if dt.code in ['X', 'Y', 'B', 'W'] else 10
                    address = int(addr_str, base)
                    break
            
            if device_type:
                self.server.set_device_value(device_type.code, address, value)
                self._log(f"デバイス設定: {device_str} = {value}")
            else:
                messagebox.showerror("エラー", f"不明なデバイス: {device_str}")
                
        except Exception as e:
            messagebox.showerror("エラー", f"設定エラー: {e}")
    
    # === クライアント制御 ===
    
    def _connect(self):
        """PLCに接続"""
        try:
            config = ConnectionConfig(
                host=self.host_var.get(),
                port=int(self.port_var.get()),
                series=self.series
            )
            
            self.client = PLCClient(config)
            self.client.connect()
            
            self._on_connected()
            self._log("PLC接続成功")
            
        except PLCClientError as e:
            messagebox.showerror("接続エラー", str(e))
            self._log(f"接続エラー: {e}")
    
    def _disconnect(self):
        """PLCから切断"""
        if self.client:
            # モニタ停止
            self._stop_monitor()
            
            self.client.disconnect()
            self.client = None
            
            self._on_disconnected()
            self._log("PLC切断")
    
    def _on_connected(self):
        """接続時の処理"""
        self.connect_btn['state'] = tk.DISABLED
        self.disconnect_btn['state'] = tk.NORMAL
        self.read_cpu_btn['state'] = tk.NORMAL
        self.run_btn['state'] = tk.NORMAL
        self.stop_btn['state'] = tk.NORMAL
        self.reset_btn['state'] = tk.NORMAL
        self.read_word_btn['state'] = tk.NORMAL
        self.read_bit_btn['state'] = tk.NORMAL
        self.write_word_btn['state'] = tk.NORMAL
        self.write_bit_btn['state'] = tk.NORMAL
        self.monitor_start_btn['state'] = tk.NORMAL
        
        self.client_status_label.config(text="接続中", foreground="green")
    
    def _on_disconnected(self):
        """切断時の処理"""
        self.connect_btn['state'] = tk.NORMAL
        self.disconnect_btn['state'] = tk.DISABLED
        self.read_cpu_btn['state'] = tk.DISABLED
        self.run_btn['state'] = tk.DISABLED
        self.stop_btn['state'] = tk.DISABLED
        self.reset_btn['state'] = tk.DISABLED
        self.read_word_btn['state'] = tk.DISABLED
        self.read_bit_btn['state'] = tk.DISABLED
        self.write_word_btn['state'] = tk.DISABLED
        self.write_bit_btn['state'] = tk.DISABLED
        self.monitor_start_btn['state'] = tk.DISABLED
        self.monitor_stop_btn['state'] = tk.DISABLED
        
        self.client_status_label.config(text="未接続", foreground="red")
    
    def _read_cpu_model(self):
        """CPU型名を読み出し"""
        if not self.client:
            return
        
        try:
            model = self.client.read_cpu_model()
            self.result_var.set(f"CPU型名: {model}")
            self._log(f"CPU型名: {model}")
        except PLCClientError as e:
            self.result_var.set(f"エラー: {e}")
            self._log(f"CPU型名読出しエラー: {e}")
    
    def _remote_run(self):
        """リモートRUN"""
        if not self.client:
            return
        
        try:
            self.client.remote_run()
            self._log("リモートRUN実行")
        except PLCClientError as e:
            messagebox.showerror("エラー", str(e))
    
    def _remote_stop(self):
        """リモートSTOP"""
        if not self.client:
            return
        
        try:
            self.client.remote_stop()
            self._log("リモートSTOP実行")
        except PLCClientError as e:
            messagebox.showerror("エラー", str(e))
    
    def _remote_reset(self):
        """リモートRESET"""
        if not self.client:
            return
        
        try:
            self.client.remote_reset()
            self._log("リモートRESET実行")
        except PLCClientError as e:
            messagebox.showerror("エラー", str(e))
    
    def _parse_device(self, device_str: str):
        """デバイス文字列を解析"""
        device_str = device_str.upper().strip()
        
        for dt in DeviceType:
            if device_str.startswith(dt.code):
                addr_str = device_str[len(dt.code):]
                base = 16 if dt.code in ['X', 'Y', 'B', 'W'] else 10
                return dt.code, int(addr_str, base)
        
        raise ValueError(f"Unknown device: {device_str}")
    
    def _read_words(self):
        """ワードを読み出し"""
        if not self.client:
            return
        
        try:
            device_code, start = self._parse_device(self.device_var.get())
            count = int(self.count_var.get())
            
            values = self.client.read_words(device_code, start, count)
            
            result = f"{device_code}{start}～: {values}"
            self.result_var.set(result)
            self._log(f"ワード読出し: {result}")
            
        except Exception as e:
            self.result_var.set(f"エラー: {e}")
            self._log(f"読出しエラー: {e}")
    
    def _read_bits(self):
        """ビットを読み出し"""
        if not self.client:
            return
        
        try:
            device_code, start = self._parse_device(self.device_var.get())
            count = int(self.count_var.get())
            
            values = self.client.read_bits(device_code, start, count)
            
            result = f"{device_code}{start}～: {[1 if v else 0 for v in values]}"
            self.result_var.set(result)
            self._log(f"ビット読出し: {result}")
            
        except Exception as e:
            self.result_var.set(f"エラー: {e}")
            self._log(f"読出しエラー: {e}")
    
    def _write_word(self):
        """ワードを書き込み"""
        if not self.client:
            return
        
        try:
            device_code, address = self._parse_device(self.device_var.get())
            value = int(self.value_var.get())
            
            self.client.write_word(device_code, address, value)
            
            result = f"{device_code}{address} = {value} 書込み完了"
            self.result_var.set(result)
            self._log(result)
            
        except Exception as e:
            self.result_var.set(f"エラー: {e}")
            self._log(f"書込みエラー: {e}")
    
    def _write_bit(self):
        """ビットを書き込み"""
        if not self.client:
            return
        
        try:
            device_code, address = self._parse_device(self.device_var.get())
            value = bool(int(self.value_var.get()))
            
            self.client.write_bit(device_code, address, value)
            
            result = f"{device_code}{address} = {1 if value else 0} 書込み完了"
            self.result_var.set(result)
            self._log(result)
            
        except Exception as e:
            self.result_var.set(f"エラー: {e}")
            self._log(f"書込みエラー: {e}")
    
    # === モニター ===
    
    def _start_monitor(self):
        """モニターを開始"""
        if not self.client or self.monitor_running:
            return
        
        self.monitor_running = True
        self.monitor_start_btn['state'] = tk.DISABLED
        self.monitor_stop_btn['state'] = tk.NORMAL
        
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        self._log("モニター開始")
    
    def _stop_monitor(self):
        """モニターを停止"""
        self.monitor_running = False
        
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1.0)
            self.monitor_thread = None
        
        self.monitor_start_btn['state'] = tk.NORMAL if self.client else tk.DISABLED
        self.monitor_stop_btn['state'] = tk.DISABLED
        
        self._log("モニター停止")
    
    def _monitor_loop(self):
        """モニターループ"""
        while self.monitor_running and self.client:
            try:
                interval = int(self.monitor_interval_var.get())
            except:
                interval = 500
            
            try:
                devices_str = self.monitor_devices_var.get()
                devices = [d.strip() for d in devices_str.split(',') if d.strip()]
                
                lines = [f"=== {datetime.now().strftime('%H:%M:%S')} ==="]
                
                for device_str in devices:
                    try:
                        device_code, address = self._parse_device(device_str)
                        device_type = DeviceType.from_code(device_code)
                        
                        if device_type and device_type.is_bit_device:
                            value = self.client.read_bit(device_code, address)
                            lines.append(f"{device_str}: {1 if value else 0}")
                        else:
                            value = self.client.read_word(device_code, address)
                            lines.append(f"{device_str}: {value}")
                            
                    except Exception as e:
                        lines.append(f"{device_str}: ERROR")
                
                # 表示更新
                self.root.after(0, lambda l=lines: self._update_monitor('\n'.join(l)))
                
            except Exception as e:
                self.root.after(0, lambda: self._update_monitor(f"Error: {e}"))
            
            time.sleep(interval / 1000.0)
    
    def _update_monitor(self, text: str):
        """モニター表示を更新"""
        self.monitor_text.delete(1.0, tk.END)
        self.monitor_text.insert(1.0, text)
    
    # === クリーンアップ ===
    
    def _on_closing(self):
        """ウィンドウを閉じる時"""
        # モニター停止
        self._stop_monitor()
        
        # クライアント切断
        if self.client:
            self.client.disconnect()
        
        # サーバー停止
        if self.server:
            self.server.stop()
        
        self.root.destroy()


def main():
    """メイン関数"""
    root = tk.Tk()
    
    # テーマ設定
    try:
        style = ttk.Style()
        if 'clam' in style.theme_names():
            style.theme_use('clam')
    except:
        pass
    
    app = PLCTesterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
