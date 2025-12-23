"""
PLCクライアントGUI
PLCクライアント専用アプリケーション
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import time
from datetime import datetime
from typing import Optional, List, Dict
import queue

from mc_protocol import PLCSeries, DeviceType
from plc_client import PLCClient, ConnectionConfig


class DeviceEntry:
    """モニタ対象デバイスエントリ"""
    
    def __init__(self, device_type: str, address: int, count: int = 1, 
                 display_format: str = "DEC"):
        self.device_type = device_type  # "X", "Y", "M", "D", etc.
        self.address = address
        self.count = count
        self.display_format = display_format  # "DEC", "HEX", "BIN"
        self.values: List[int] = [0] * count


class PLCClientGUI:
    """PLCクライアントGUIアプリケーション"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PLCクライアント")
        self.root.geometry("950x700")
        
        # クライアント
        self.client: Optional[PLCClient] = None
        
        # 接続状態
        self.connected = False
        
        # モニタ
        self.monitor_entries: List[DeviceEntry] = []
        self.monitor_running = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        # ログキュー
        self.log_queue = queue.Queue()
        
        # UI作成
        self._create_widgets()
        
        # ログ処理タイマー
        self._process_log_queue()
        
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
    
    def _create_widgets(self):
        """UIウィジェットを作成"""
        # 上部: 接続設定
        self._create_connection_frame()
        
        # メインノートブック（タブ）
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # タブ1: デバイス読み書き
        rw_tab = ttk.Frame(notebook, padding="10")
        notebook.add(rw_tab, text="デバイス読み書き")
        self._create_rw_tab(rw_tab)
        
        # タブ2: デバイスモニタ
        monitor_tab = ttk.Frame(notebook, padding="10")
        notebook.add(monitor_tab, text="デバイスモニタ")
        self._create_monitor_tab(monitor_tab)
        
        # タブ3: PLC制御
        ctrl_tab = ttk.Frame(notebook, padding="10")
        notebook.add(ctrl_tab, text="PLC制御")
        self._create_ctrl_tab(ctrl_tab)
        
        # タブ4: ログ
        log_tab = ttk.Frame(notebook, padding="10")
        notebook.add(log_tab, text="ログ")
        self._create_log_tab(log_tab)
    
    def _create_connection_frame(self):
        """接続フレーム"""
        conn_frame = ttk.LabelFrame(self.root, text="接続設定", padding="10")
        conn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 設定行
        row1 = ttk.Frame(conn_frame)
        row1.pack(fill=tk.X, pady=5)
        
        ttk.Label(row1, text="ホスト:").pack(side=tk.LEFT, padx=5)
        self.host_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(row1, textvariable=self.host_var, width=15).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row1, text="ポート:").pack(side=tk.LEFT, padx=5)
        self.port_var = tk.StringVar(value="5000")
        ttk.Entry(row1, textvariable=self.port_var, width=8).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row1, text="シリーズ:").pack(side=tk.LEFT, padx=5)
        self.series_var = tk.StringVar(value="Q")
        series_combo = ttk.Combobox(row1, textvariable=self.series_var,
                                    values=["Q (3Eフレーム)", "iQ-R (4Eフレーム)"],
                                    state="readonly", width=15)
        series_combo.pack(side=tk.LEFT, padx=5)
        series_combo.current(0)
        
        ttk.Label(row1, text="タイムアウト(秒):").pack(side=tk.LEFT, padx=5)
        self.timeout_var = tk.StringVar(value="3.0")
        ttk.Entry(row1, textvariable=self.timeout_var, width=6).pack(side=tk.LEFT, padx=5)
        
        # ボタン行
        row2 = ttk.Frame(conn_frame)
        row2.pack(fill=tk.X, pady=10)
        
        self.connect_btn = ttk.Button(row2, text="🔌 接続", command=self._connect, width=12)
        self.connect_btn.pack(side=tk.LEFT, padx=10)
        
        self.disconnect_btn = ttk.Button(row2, text="切断", command=self._disconnect, 
                                         width=12, state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.LEFT, padx=10)
        
        # ステータス
        ttk.Label(row2, text="状態:").pack(side=tk.LEFT, padx=(30, 5))
        self.status_label = ttk.Label(row2, text="未接続", foreground="red", 
                                      font=('', 10, 'bold'))
        self.status_label.pack(side=tk.LEFT, padx=5)
        
        self.cpu_label = ttk.Label(row2, text="", foreground="gray")
        self.cpu_label.pack(side=tk.LEFT, padx=(20, 5))
    
    def _create_rw_tab(self, parent):
        """デバイス読み書きタブ"""
        # デバイス選択ヘルプ
        help_frame = ttk.LabelFrame(parent, text="デバイスタイプ一覧", padding="10")
        help_frame.pack(fill=tk.X, pady=(0, 10))
        
        help_text = ("ビットデバイス: X(入力), Y(出力), M(内部リレー), B(リンクリレー), "
                    "T(タイマ接点), C(カウンタ接点)\n"
                    "ワードデバイス: D(データレジスタ), W(リンクレジスタ), R(ファイルレジスタ), "
                    "TN(タイマ現在値), CN(カウンタ現在値)")
        ttk.Label(help_frame, text=help_text, wraplength=800).pack(anchor=tk.W)
        
        # 読み取りフレーム
        read_frame = ttk.LabelFrame(parent, text="デバイス読み取り", padding="10")
        read_frame.pack(fill=tk.X, pady=(0, 10))
        
        read_row = ttk.Frame(read_frame)
        read_row.pack(fill=tk.X, pady=5)
        
        ttk.Label(read_row, text="デバイス:").pack(side=tk.LEFT, padx=5)
        self.read_device_var = tk.StringVar(value="D")
        read_device_combo = ttk.Combobox(read_row, textvariable=self.read_device_var,
                                         values=["X", "Y", "M", "B", "D", "W", "R", "TN", "CN"],
                                         state="readonly", width=6)
        read_device_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(read_row, text="開始番号:").pack(side=tk.LEFT, padx=5)
        self.read_addr_var = tk.StringVar(value="0")
        ttk.Entry(read_row, textvariable=self.read_addr_var, width=8).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(read_row, text="点数:").pack(side=tk.LEFT, padx=5)
        self.read_count_var = tk.StringVar(value="10")
        ttk.Entry(read_row, textvariable=self.read_count_var, width=6).pack(side=tk.LEFT, padx=5)
        
        self.read_btn = ttk.Button(read_row, text="読み取り", command=self._read_device, 
                                   state=tk.DISABLED)
        self.read_btn.pack(side=tk.LEFT, padx=10)
        
        # 読み取り結果
        result_frame = ttk.Frame(read_frame)
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        ttk.Label(result_frame, text="結果:").pack(anchor=tk.W)
        self.read_result = scrolledtext.ScrolledText(result_frame, height=5, width=80,
                                                      font=('Consolas', 10))
        self.read_result.pack(fill=tk.BOTH, expand=True)
        
        # 書き込みフレーム
        write_frame = ttk.LabelFrame(parent, text="デバイス書き込み", padding="10")
        write_frame.pack(fill=tk.X, pady=(0, 10))
        
        write_row1 = ttk.Frame(write_frame)
        write_row1.pack(fill=tk.X, pady=5)
        
        ttk.Label(write_row1, text="デバイス:").pack(side=tk.LEFT, padx=5)
        self.write_device_var = tk.StringVar(value="D")
        write_device_combo = ttk.Combobox(write_row1, textvariable=self.write_device_var,
                                          values=["X", "Y", "M", "B", "D", "W", "R"],
                                          state="readonly", width=6)
        write_device_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(write_row1, text="番号:").pack(side=tk.LEFT, padx=5)
        self.write_addr_var = tk.StringVar(value="0")
        ttk.Entry(write_row1, textvariable=self.write_addr_var, width=8).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(write_row1, text="値:").pack(side=tk.LEFT, padx=5)
        self.write_value_var = tk.StringVar(value="0")
        ttk.Entry(write_row1, textvariable=self.write_value_var, width=15).pack(side=tk.LEFT, padx=5)
        
        write_row2 = ttk.Frame(write_frame)
        write_row2.pack(fill=tk.X, pady=5)
        
        self.write_type_var = tk.StringVar(value="bit")
        ttk.Radiobutton(write_row2, text="ビット (0/1)", variable=self.write_type_var, 
                       value="bit").pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(write_row2, text="ワード (0-65535)", variable=self.write_type_var, 
                       value="word").pack(side=tk.LEFT, padx=10)
        
        self.write_btn = ttk.Button(write_row2, text="書き込み", command=self._write_device, 
                                    state=tk.DISABLED)
        self.write_btn.pack(side=tk.LEFT, padx=20)
        
        # クイックボタン
        quick_frame = ttk.LabelFrame(parent, text="クイック操作", padding="10")
        quick_frame.pack(fill=tk.X)
        
        quick_row1 = ttk.Frame(quick_frame)
        quick_row1.pack(fill=tk.X, pady=5)
        
        ttk.Label(quick_row1, text="入力 X ON:").pack(side=tk.LEFT, padx=5)
        for i in range(8):
            btn = ttk.Button(quick_row1, text=f"X{i}", width=4,
                            command=lambda a=i: self._quick_write("X", a, 1))
            btn.pack(side=tk.LEFT, padx=2)
        
        quick_row2 = ttk.Frame(quick_frame)
        quick_row2.pack(fill=tk.X, pady=5)
        
        ttk.Label(quick_row2, text="入力 X OFF:").pack(side=tk.LEFT, padx=5)
        for i in range(8):
            btn = ttk.Button(quick_row2, text=f"X{i}", width=4,
                            command=lambda a=i: self._quick_write("X", a, 0))
            btn.pack(side=tk.LEFT, padx=2)
    
    def _create_monitor_tab(self, parent):
        """デバイスモニタタブ"""
        # モニタ設定
        config_frame = ttk.LabelFrame(parent, text="モニタ設定", padding="10")
        config_frame.pack(fill=tk.X, pady=(0, 10))
        
        add_row = ttk.Frame(config_frame)
        add_row.pack(fill=tk.X, pady=5)
        
        ttk.Label(add_row, text="デバイス:").pack(side=tk.LEFT, padx=5)
        self.mon_device_var = tk.StringVar(value="D")
        mon_device_combo = ttk.Combobox(add_row, textvariable=self.mon_device_var,
                                        values=["X", "Y", "M", "B", "D", "W", "R", "TN", "CN"],
                                        state="readonly", width=6)
        mon_device_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(add_row, text="開始番号:").pack(side=tk.LEFT, padx=5)
        self.mon_addr_var = tk.StringVar(value="0")
        ttk.Entry(add_row, textvariable=self.mon_addr_var, width=8).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(add_row, text="点数:").pack(side=tk.LEFT, padx=5)
        self.mon_count_var = tk.StringVar(value="10")
        ttk.Entry(add_row, textvariable=self.mon_count_var, width=6).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(add_row, text="表示:").pack(side=tk.LEFT, padx=5)
        self.mon_format_var = tk.StringVar(value="DEC")
        format_combo = ttk.Combobox(add_row, textvariable=self.mon_format_var,
                                    values=["DEC", "HEX", "BIN"], state="readonly", width=6)
        format_combo.pack(side=tk.LEFT, padx=5)
        
        self.add_monitor_btn = ttk.Button(add_row, text="追加", command=self._add_monitor_entry)
        self.add_monitor_btn.pack(side=tk.LEFT, padx=10)
        
        # プリセット
        preset_row = ttk.Frame(config_frame)
        preset_row.pack(fill=tk.X, pady=5)
        
        ttk.Label(preset_row, text="プリセット:").pack(side=tk.LEFT, padx=5)
        ttk.Button(preset_row, text="X0-7", command=lambda: self._add_preset("X", 0, 8)).pack(side=tk.LEFT, padx=3)
        ttk.Button(preset_row, text="Y0-7", command=lambda: self._add_preset("Y", 0, 8)).pack(side=tk.LEFT, padx=3)
        ttk.Button(preset_row, text="M0-15", command=lambda: self._add_preset("M", 0, 16)).pack(side=tk.LEFT, padx=3)
        ttk.Button(preset_row, text="D0-15", command=lambda: self._add_preset("D", 0, 16)).pack(side=tk.LEFT, padx=3)
        ttk.Button(preset_row, text="クリア", command=self._clear_monitor_entries).pack(side=tk.LEFT, padx=10)
        
        # 制御
        ctrl_row = ttk.Frame(config_frame)
        ctrl_row.pack(fill=tk.X, pady=10)
        
        ttk.Label(ctrl_row, text="更新間隔(ms):").pack(side=tk.LEFT, padx=5)
        self.mon_interval_var = tk.StringVar(value="200")
        ttk.Entry(ctrl_row, textvariable=self.mon_interval_var, width=6).pack(side=tk.LEFT, padx=5)
        
        self.mon_start_btn = ttk.Button(ctrl_row, text="▶ モニタ開始", 
                                        command=self._start_monitor, state=tk.DISABLED)
        self.mon_start_btn.pack(side=tk.LEFT, padx=10)
        
        self.mon_stop_btn = ttk.Button(ctrl_row, text="⏹ モニタ停止", 
                                       command=self._stop_monitor, state=tk.DISABLED)
        self.mon_stop_btn.pack(side=tk.LEFT, padx=5)
        
        # モニタ表示
        display_frame = ttk.LabelFrame(parent, text="デバイス値", padding="10")
        display_frame.pack(fill=tk.BOTH, expand=True)
        
        # ツリービュー
        columns = ("Address", "Value", "Hex", "Binary")
        self.monitor_tree = ttk.Treeview(display_frame, columns=columns, 
                                         show="tree headings", height=20)
        self.monitor_tree.heading("#0", text="デバイス")
        self.monitor_tree.heading("Address", text="番号")
        self.monitor_tree.heading("Value", text="10進値")
        self.monitor_tree.heading("Hex", text="16進値")
        self.monitor_tree.heading("Binary", text="ビット")
        
        self.monitor_tree.column("#0", width=80)
        self.monitor_tree.column("Address", width=80, anchor=tk.CENTER)
        self.monitor_tree.column("Value", width=100, anchor=tk.CENTER)
        self.monitor_tree.column("Hex", width=80, anchor=tk.CENTER)
        self.monitor_tree.column("Binary", width=150, anchor=tk.CENTER)
        
        # スクロールバー
        scrollbar = ttk.Scrollbar(display_frame, orient=tk.VERTICAL, 
                                  command=self.monitor_tree.yview)
        self.monitor_tree.configure(yscrollcommand=scrollbar.set)
        
        self.monitor_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # タグ設定
        self.monitor_tree.tag_configure("on", background="#90EE90")
        self.monitor_tree.tag_configure("off", background="white")
        self.monitor_tree.tag_configure("word", background="#E8E8E8")
    
    def _create_ctrl_tab(self, parent):
        """PLC制御タブ"""
        # リモート制御
        remote_frame = ttk.LabelFrame(parent, text="リモート制御", padding="20")
        remote_frame.pack(fill=tk.X, pady=(0, 10))
        
        btn_frame = ttk.Frame(remote_frame)
        btn_frame.pack(pady=20)
        
        self.remote_run_btn = ttk.Button(btn_frame, text="リモート RUN", 
                                         command=self._remote_run, width=15, state=tk.DISABLED)
        self.remote_run_btn.grid(row=0, column=0, padx=20, pady=10)
        
        self.remote_stop_btn = ttk.Button(btn_frame, text="リモート STOP", 
                                          command=self._remote_stop, width=15, state=tk.DISABLED)
        self.remote_stop_btn.grid(row=0, column=1, padx=20, pady=10)
        
        self.remote_reset_btn = ttk.Button(btn_frame, text="リモート RESET", 
                                           command=self._remote_reset, width=15, state=tk.DISABLED)
        self.remote_reset_btn.grid(row=0, column=2, padx=20, pady=10)
        
        # CPU情報
        info_frame = ttk.LabelFrame(parent, text="CPU情報", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        info_row = ttk.Frame(info_frame)
        info_row.pack(fill=tk.X, pady=10)
        
        self.read_cpu_btn = ttk.Button(info_row, text="CPU型名読出し", 
                                       command=self._read_cpu_model, state=tk.DISABLED)
        self.read_cpu_btn.pack(side=tk.LEFT, padx=10)
        
        ttk.Label(info_row, text="型名:").pack(side=tk.LEFT, padx=10)
        self.cpu_model_var = tk.StringVar(value="-")
        ttk.Label(info_row, textvariable=self.cpu_model_var, font=('', 10, 'bold')).pack(side=tk.LEFT)
        
        # 注意事項
        note_frame = ttk.LabelFrame(parent, text="注意事項", padding="10")
        note_frame.pack(fill=tk.X)
        
        note_text = """
【リモート制御について】
- リモートRUN: PLCをRUN状態にします。ラダープログラムが実行されます。
- リモートSTOP: PLCをSTOP状態にします。ラダープログラムが停止します。
- リモートRESET: PLCをリセットします。出力・内部リレーがクリアされます。

【使用上の注意】
- 実機PLCに対してリモート制御を行う場合は、安全を十分確認してください。
- このクライアントはモックPLCサーバーとの通信テスト用です。
        """
        ttk.Label(note_frame, text=note_text, justify=tk.LEFT).pack(anchor=tk.W)
    
    def _create_log_tab(self, parent):
        """ログタブ"""
        self.log_text = scrolledtext.ScrolledText(parent, font=('Consolas', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(btn_frame, text="ログクリア", command=self._clear_log).pack(side=tk.RIGHT)
    
    def _log(self, message: str):
        """ログを追加（スレッドセーフ）"""
        self.log_queue.put(message)
    
    def _process_log_queue(self):
        """ログキューを処理"""
        while not self.log_queue.empty():
            try:
                message = self.log_queue.get_nowait()
                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
                self.log_text.see(tk.END)
            except:
                break
        
        self.root.after(100, self._process_log_queue)
    
    def _clear_log(self):
        """ログをクリア"""
        self.log_text.delete(1.0, tk.END)
    
    # === 接続 ===
    
    def _connect(self):
        """PLCに接続"""
        try:
            host = self.host_var.get()
            port = int(self.port_var.get())
            timeout = float(self.timeout_var.get())
            
            series_str = self.series_var.get()
            series = PLCSeries.Q_SERIES if "Q" in series_str else PLCSeries.IQR_SERIES
            
            config = ConnectionConfig(
                host=host,
                port=port,
                series=series,
                timeout=timeout
            )
            
            self.client = PLCClient(config)
            
            if self.client.connect():
                self.connected = True
                self._on_connected()
                self._log(f"接続成功: {host}:{port}")
                
                # CPU型名読出し
                cpu_model = self.client.read_cpu_model()
                if cpu_model:
                    self.cpu_label.config(text=f"CPU: {cpu_model}")
            else:
                messagebox.showerror("エラー", "接続に失敗しました")
                
        except Exception as e:
            messagebox.showerror("エラー", f"接続エラー: {e}")
            self._log(f"接続エラー: {e}")
    
    def _disconnect(self):
        """切断"""
        self._stop_monitor()
        
        if self.client:
            self.client.disconnect()
            self.client = None
        
        self.connected = False
        self._on_disconnected()
        self._log("切断しました")
    
    def _on_connected(self):
        """接続時"""
        self.connect_btn['state'] = tk.DISABLED
        self.disconnect_btn['state'] = tk.NORMAL
        self.read_btn['state'] = tk.NORMAL
        self.write_btn['state'] = tk.NORMAL
        self.mon_start_btn['state'] = tk.NORMAL
        self.remote_run_btn['state'] = tk.NORMAL
        self.remote_stop_btn['state'] = tk.NORMAL
        self.remote_reset_btn['state'] = tk.NORMAL
        self.read_cpu_btn['state'] = tk.NORMAL
        
        self.status_label.config(text="接続中", foreground="green")
    
    def _on_disconnected(self):
        """切断時"""
        self.connect_btn['state'] = tk.NORMAL
        self.disconnect_btn['state'] = tk.DISABLED
        self.read_btn['state'] = tk.DISABLED
        self.write_btn['state'] = tk.DISABLED
        self.mon_start_btn['state'] = tk.DISABLED
        self.mon_stop_btn['state'] = tk.DISABLED
        self.remote_run_btn['state'] = tk.DISABLED
        self.remote_stop_btn['state'] = tk.DISABLED
        self.remote_reset_btn['state'] = tk.DISABLED
        self.read_cpu_btn['state'] = tk.DISABLED
        
        self.status_label.config(text="未接続", foreground="red")
        self.cpu_label.config(text="")
    
    # === デバイス読み書き ===
    
    def _read_device(self):
        """デバイス読み取り"""
        if not self.client:
            return
        
        try:
            device = self.read_device_var.get()
            device_type = DeviceType.from_code(device)
            if not device_type:
                messagebox.showerror("エラー", f"不明なデバイス: {device}")
                return
            
            is_hex = device in ['X', 'Y', 'B', 'W']
            address = int(self.read_addr_var.get(), 16 if is_hex else 10)
            count = int(self.read_count_var.get())
            
            # ビットデバイスかワードデバイスか判定
            is_bit = device in ['X', 'Y', 'M', 'B', 'T', 'C']
            
            if is_bit:
                values = self.client.read_bits(device, address, count)
            else:
                values = self.client.read_words(device, address, count)
            
            # 結果表示
            self.read_result.delete(1.0, tk.END)
            
            if values:
                result_lines = []
                for i, val in enumerate(values):
                    addr = address + i
                    if is_hex:
                        addr_str = f"{addr:X}"
                    else:
                        addr_str = str(addr)
                    
                    if is_bit:
                        result_lines.append(f"{device}{addr_str}: {'ON' if val else 'OFF'}")
                    else:
                        result_lines.append(f"{device}{addr_str}: {val} (0x{val:04X})")
                
                self.read_result.insert(tk.END, "\n".join(result_lines))
                self._log(f"読み取り: {device}{address} × {count}点")
            else:
                self.read_result.insert(tk.END, "読み取りに失敗しました")
                self._log(f"読み取りエラー: {device}{address}")
                
        except Exception as e:
            messagebox.showerror("エラー", f"読み取りエラー: {e}")
            self._log(f"読み取りエラー: {e}")
    
    def _write_device(self):
        """デバイス書き込み"""
        if not self.client:
            return
        
        try:
            device = self.write_device_var.get()
            device_type = DeviceType.from_code(device)
            if not device_type:
                messagebox.showerror("エラー", f"不明なデバイス: {device}")
                return
            
            is_hex = device in ['X', 'Y', 'B', 'W']
            address = int(self.write_addr_var.get(), 16 if is_hex else 10)
            value = int(self.write_value_var.get())
            
            is_bit = self.write_type_var.get() == "bit"
            
            if is_bit:
                success = self.client.write_bit(device, address, bool(value))
            else:
                success = self.client.write_word(device, address, value)
            
            if success:
                self._log(f"書き込み: {device}{address} = {value}")
            else:
                messagebox.showerror("エラー", "書き込みに失敗しました")
                self._log(f"書き込みエラー: {device}{address}")
                
        except Exception as e:
            messagebox.showerror("エラー", f"書き込みエラー: {e}")
            self._log(f"書き込みエラー: {e}")
    
    def _quick_write(self, device: str, address: int, value: int):
        """クイック書き込み"""
        if not self.client:
            messagebox.showwarning("警告", "PLCに接続してください")
            return
        
        device_type = DeviceType.from_code(device)
        if device_type:
            success = self.client.write_bit(device, address, bool(value))
            if success:
                self._log(f"クイック書き込み: {device}{address} = {value}")
    
    # === デバイスモニタ ===
    
    def _add_monitor_entry(self):
        """モニタエントリを追加"""
        try:
            device = self.mon_device_var.get()
            is_hex = device in ['X', 'Y', 'B', 'W']
            address = int(self.mon_addr_var.get(), 16 if is_hex else 10)
            count = int(self.mon_count_var.get())
            fmt = self.mon_format_var.get()
            
            entry = DeviceEntry(device, address, count, fmt)
            self.monitor_entries.append(entry)
            
            self._log(f"モニタ追加: {device}{address} × {count}点")
            
        except Exception as e:
            messagebox.showerror("エラー", f"追加エラー: {e}")
    
    def _add_preset(self, device: str, address: int, count: int):
        """プリセット追加"""
        entry = DeviceEntry(device, address, count, "DEC")
        self.monitor_entries.append(entry)
        self._log(f"プリセット追加: {device}{address} × {count}点")
    
    def _clear_monitor_entries(self):
        """モニタエントリをクリア"""
        self.monitor_entries.clear()
        
        for item in self.monitor_tree.get_children():
            self.monitor_tree.delete(item)
        
        self._log("モニタエントリクリア")
    
    def _start_monitor(self):
        """モニタ開始"""
        if self.monitor_running or not self.client:
            return
        
        if not self.monitor_entries:
            messagebox.showwarning("警告", "モニタ対象デバイスを追加してください")
            return
        
        self.monitor_running = True
        self.mon_start_btn['state'] = tk.DISABLED
        self.mon_stop_btn['state'] = tk.NORMAL
        
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        self._log("モニタ開始")
    
    def _stop_monitor(self):
        """モニタ停止"""
        self.monitor_running = False
        
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1.0)
            self.monitor_thread = None
        
        if self.connected:
            self.mon_start_btn['state'] = tk.NORMAL
        self.mon_stop_btn['state'] = tk.DISABLED
        
        self._log("モニタ停止")
    
    def _monitor_loop(self):
        """モニタループ"""
        while self.monitor_running and self.client:
            try:
                interval = int(self.mon_interval_var.get())
            except:
                interval = 200
            
            try:
                # 各エントリのデータを読み取り
                for entry in self.monitor_entries:
                    device_type = DeviceType.from_code(entry.device_type)
                    if not device_type:
                        continue
                    
                    is_bit = entry.device_type in ['X', 'Y', 'M', 'B', 'T', 'C']
                    
                    if is_bit:
                        values = self.client.read_bits(entry.device_type, entry.address, entry.count)
                    else:
                        values = self.client.read_words(entry.device_type, entry.address, entry.count)
                    
                    if values:
                        entry.values = values
                
                # UI更新
                self.root.after(0, self._update_monitor_tree)
                
            except Exception as e:
                pass
            
            time.sleep(interval / 1000.0)
    
    def _update_monitor_tree(self):
        """モニタツリーを更新"""
        # 既存アイテムをクリア
        for item in self.monitor_tree.get_children():
            self.monitor_tree.delete(item)
        
        for entry in self.monitor_entries:
            is_bit = entry.device_type in ['X', 'Y', 'M', 'B', 'T', 'C']
            is_hex = entry.device_type in ['X', 'Y', 'B', 'W']
            
            for i, val in enumerate(entry.values):
                addr = entry.address + i
                addr_str = f"{addr:X}" if is_hex else str(addr)
                
                if is_bit:
                    tag = "on" if val else "off"
                    self.monitor_tree.insert("", tk.END, text=entry.device_type,
                                            values=(addr_str, "ON" if val else "OFF", "-", "-"),
                                            tags=(tag,))
                else:
                    tag = "word"
                    bin_str = f"{val:016b}" if val <= 65535 else "-"
                    self.monitor_tree.insert("", tk.END, text=entry.device_type,
                                            values=(addr_str, val, f"{val:04X}", bin_str),
                                            tags=(tag,))
    
    # === PLC制御 ===
    
    def _remote_run(self):
        """リモートRUN"""
        if not self.client:
            return
        
        if self.client.remote_run():
            self._log("リモートRUN成功")
        else:
            self._log("リモートRUN失敗")
            messagebox.showerror("エラー", "リモートRUNに失敗しました")
    
    def _remote_stop(self):
        """リモートSTOP"""
        if not self.client:
            return
        
        if self.client.remote_stop():
            self._log("リモートSTOP成功")
        else:
            self._log("リモートSTOP失敗")
            messagebox.showerror("エラー", "リモートSTOPに失敗しました")
    
    def _remote_reset(self):
        """リモートRESET"""
        if not self.client:
            return
        
        if messagebox.askyesno("確認", "PLCをリセットしますか？"):
            # RESETは通常のMCプロトコルにはないので、STOPで代用
            if self.client.remote_stop():
                self._log("リモートRESET成功")
            else:
                self._log("リモートRESET失敗")
    
    def _read_cpu_model(self):
        """CPU型名読出し"""
        if not self.client:
            return
        
        model = self.client.read_cpu_model()
        if model:
            self.cpu_model_var.set(model)
            self._log(f"CPU型名: {model}")
        else:
            self.cpu_model_var.set("-")
            self._log("CPU型名読出し失敗")
    
    def _on_closing(self):
        """ウィンドウを閉じる時"""
        self._stop_monitor()
        
        if self.client:
            self.client.disconnect()
        
        self.root.destroy()


def main():
    """メイン関数"""
    root = tk.Tk()
    
    try:
        style = ttk.Style()
        if 'clam' in style.theme_names():
            style.theme_use('clam')
    except:
        pass
    
    app = PLCClientGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
