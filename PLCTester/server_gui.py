"""
PLCサーバーGUI
モックPLCサーバー専用アプリケーション
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import threading
import time
from datetime import datetime
from typing import Optional, Dict
import os

from mc_protocol import PLCSeries, DeviceType
from mock_plc_server import MockPLCServer, PLCState
from ladder_gxworks import (
    GXLadder, GXProjectLoader,
    create_gx_sample_1, create_gx_sample_2, create_gx_sample_3,
    create_gx_sample_4, create_gx_sample_5, SAMPLE_LADDER_TEXT
)


class PLCServerGUI:
    """PLCサーバーGUIアプリケーション"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("モックPLCサーバー")
        self.root.geometry("900x750")
        
        # サーバー
        self.server: Optional[MockPLCServer] = None
        
        # 設定
        self.host = "127.0.0.1"
        self.port = 5000
        self.series = PLCSeries.Q_SERIES
        
        # デバイスモニタ
        self.device_monitor_running = False
        self.device_monitor_thread: Optional[threading.Thread] = None
        
        # UI作成
        self._create_widgets()
        
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
    
    def _create_widgets(self):
        """UIウィジェットを作成"""
        # メインノートブック（タブ）
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # タブ1: サーバー制御
        server_tab = ttk.Frame(notebook, padding="10")
        notebook.add(server_tab, text="サーバー制御")
        self._create_server_tab(server_tab)
        
        # タブ2: ラダープログラム
        ladder_tab = ttk.Frame(notebook, padding="10")
        notebook.add(ladder_tab, text="ラダープログラム")
        self._create_ladder_tab(ladder_tab)
        
        # タブ3: デバイス状態
        device_tab = ttk.Frame(notebook, padding="10")
        notebook.add(device_tab, text="デバイス状態")
        self._create_device_tab(device_tab)
        
        # タブ4: ログ
        log_tab = ttk.Frame(notebook, padding="10")
        notebook.add(log_tab, text="ログ")
        self._create_log_tab(log_tab)
    
    def _create_server_tab(self, parent):
        """サーバー制御タブ"""
        # 設定フレーム
        config_frame = ttk.LabelFrame(parent, text="サーバー設定", padding="10")
        config_frame.pack(fill=tk.X, pady=(0, 10))
        
        # ホスト
        ttk.Label(config_frame, text="ホスト:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.host_var = tk.StringVar(value=self.host)
        ttk.Entry(config_frame, textvariable=self.host_var, width=15).grid(row=0, column=1, padx=5, pady=5)
        
        # ポート
        ttk.Label(config_frame, text="ポート:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        self.port_var = tk.StringVar(value=str(self.port))
        ttk.Entry(config_frame, textvariable=self.port_var, width=8).grid(row=0, column=3, padx=5, pady=5)
        
        # シリーズ
        ttk.Label(config_frame, text="シリーズ:").grid(row=0, column=4, sticky=tk.W, padx=5, pady=5)
        self.series_var = tk.StringVar(value="Q")
        series_combo = ttk.Combobox(config_frame, textvariable=self.series_var,
                                    values=["Q (3Eフレーム)", "iQ-R (4Eフレーム)"], 
                                    state="readonly", width=15)
        series_combo.grid(row=0, column=5, padx=5, pady=5)
        series_combo.current(0)
        
        # 制御フレーム
        ctrl_frame = ttk.LabelFrame(parent, text="サーバー制御", padding="10")
        ctrl_frame.pack(fill=tk.X, pady=(0, 10))
        
        btn_frame = ttk.Frame(ctrl_frame)
        btn_frame.pack(pady=10)
        
        self.start_btn = ttk.Button(btn_frame, text="▶ サーバー起動", 
                                    command=self._start_server, width=15)
        self.start_btn.grid(row=0, column=0, padx=10)
        
        self.stop_btn = ttk.Button(btn_frame, text="⏹ サーバー停止", 
                                   command=self._stop_server, width=15, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=1, padx=10)
        
        # ステータスフレーム
        status_frame = ttk.LabelFrame(parent, text="ステータス", padding="10")
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        # サーバー状態
        row1 = ttk.Frame(status_frame)
        row1.pack(fill=tk.X, pady=5)
        
        ttk.Label(row1, text="サーバー:", width=12).pack(side=tk.LEFT)
        self.server_status = ttk.Label(row1, text="停止", foreground="red", font=('', 10, 'bold'))
        self.server_status.pack(side=tk.LEFT, padx=10)
        
        ttk.Label(row1, text="PLC状態:", width=12).pack(side=tk.LEFT, padx=(30, 0))
        self.plc_status = ttk.Label(row1, text="-", font=('', 10, 'bold'))
        self.plc_status.pack(side=tk.LEFT, padx=10)
        
        # クライアント状態
        row2 = ttk.Frame(status_frame)
        row2.pack(fill=tk.X, pady=5)
        
        ttk.Label(row2, text="クライアント:", width=12).pack(side=tk.LEFT)
        self.client_status = ttk.Label(row2, text="未接続", foreground="gray")
        self.client_status.pack(side=tk.LEFT, padx=10)
        
        # PLC制御（サーバー側）
        plc_frame = ttk.LabelFrame(parent, text="PLC制御（サーバー側）", padding="10")
        plc_frame.pack(fill=tk.X, pady=(0, 10))
        
        plc_btn_frame = ttk.Frame(plc_frame)
        plc_btn_frame.pack(pady=5)
        
        self.run_btn = ttk.Button(plc_btn_frame, text="RUN", command=self._plc_run, 
                                  width=10, state=tk.DISABLED)
        self.run_btn.grid(row=0, column=0, padx=5)
        
        self.stop_plc_btn = ttk.Button(plc_btn_frame, text="STOP", command=self._plc_stop, 
                                       width=10, state=tk.DISABLED)
        self.stop_plc_btn.grid(row=0, column=1, padx=5)
        
        self.reset_btn = ttk.Button(plc_btn_frame, text="RESET", command=self._plc_reset, 
                                    width=10, state=tk.DISABLED)
        self.reset_btn.grid(row=0, column=2, padx=5)
        
        # 情報
        info_frame = ttk.LabelFrame(parent, text="接続情報", padding="10")
        info_frame.pack(fill=tk.BOTH, expand=True)
        
        info_text = f"""
【モックPLCサーバーについて】

このサーバーは三菱PLCのMCプロトコルをシミュレートします。
クライアントアプリケーション開発のテストに使用できます。

【対応機能】
- 一括読出し / 一括書込み
- リモートRUN / STOP / RESET
- CPU型名読出し
- ラダープログラム実行

【使用方法】
1. サーバー設定を確認して「サーバー起動」をクリック
2. ラダープログラムタブでプログラムをロード
3. クライアントアプリから接続してテスト
        """
        
        info_label = ttk.Label(info_frame, text=info_text, justify=tk.LEFT)
        info_label.pack(anchor=tk.W)
    
    def _create_ladder_tab(self, parent):
        """ラダープログラムタブ"""
        # サンプルプログラム
        sample_frame = ttk.LabelFrame(parent, text="サンプルプログラム", padding="10")
        sample_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(sample_frame, text="プログラム選択:").grid(row=0, column=0, sticky=tk.W, pady=5)
        
        self.sample_var = tk.StringVar(value="自己保持回路")
        sample_combo = ttk.Combobox(sample_frame, textvariable=self.sample_var,
                                    values=["自己保持回路", "タイマ回路", "カウンタ回路", 
                                           "データ演算", "複雑条件"],
                                    state="readonly", width=20)
        sample_combo.grid(row=0, column=1, padx=10, pady=5)
        
        self.load_sample_btn = ttk.Button(sample_frame, text="ロード", 
                                          command=self._load_sample, state=tk.DISABLED)
        self.load_sample_btn.grid(row=0, column=2, padx=5, pady=5)
        
        # ファイルからロード
        file_frame = ttk.LabelFrame(parent, text="ファイルからロード", padding="10")
        file_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(file_frame, text="GX Works2形式テキストファイル (.txt):").pack(anchor=tk.W)
        
        file_btn_frame = ttk.Frame(file_frame)
        file_btn_frame.pack(fill=tk.X, pady=5)
        
        self.file_path_var = tk.StringVar()
        ttk.Entry(file_btn_frame, textvariable=self.file_path_var, width=50).pack(side=tk.LEFT, padx=(0, 10))
        
        self.browse_btn = ttk.Button(file_btn_frame, text="参照...", command=self._browse_file)
        self.browse_btn.pack(side=tk.LEFT, padx=5)
        
        self.load_file_btn = ttk.Button(file_btn_frame, text="ロード", 
                                        command=self._load_file, state=tk.DISABLED)
        self.load_file_btn.pack(side=tk.LEFT, padx=5)
        
        # ラダーエディタ
        editor_frame = ttk.LabelFrame(parent, text="ラダープログラムエディタ（GX Works2形式）", padding="10")
        editor_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.ladder_editor = scrolledtext.ScrolledText(editor_frame, width=80, height=15,
                                                        font=('Consolas', 10))
        self.ladder_editor.pack(fill=tk.BOTH, expand=True)
        self.ladder_editor.insert(tk.END, SAMPLE_LADDER_TEXT)
        
        editor_btn_frame = ttk.Frame(editor_frame)
        editor_btn_frame.pack(fill=tk.X, pady=5)
        
        self.compile_btn = ttk.Button(editor_btn_frame, text="コンパイル＆ロード", 
                                      command=self._compile_ladder, state=tk.DISABLED)
        self.compile_btn.pack(side=tk.LEFT, padx=5)
        
        self.clear_ladder_btn = ttk.Button(editor_btn_frame, text="クリア", 
                                           command=self._clear_ladder, state=tk.DISABLED)
        self.clear_ladder_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(editor_btn_frame, text="サンプル挿入", 
                   command=self._insert_sample).pack(side=tk.LEFT, padx=5)
        
        # 現在のプログラム
        current_frame = ttk.LabelFrame(parent, text="ロード済みプログラム", padding="10")
        current_frame.pack(fill=tk.X)
        
        self.current_program_var = tk.StringVar(value="なし")
        ttk.Label(current_frame, textvariable=self.current_program_var, 
                 font=('', 10, 'bold')).pack(anchor=tk.W)
    
    def _create_device_tab(self, parent):
        """デバイス状態タブ"""
        # デバイス設定
        set_frame = ttk.LabelFrame(parent, text="デバイス設定（サーバー側直接操作）", padding="10")
        set_frame.pack(fill=tk.X, pady=(0, 10))
        
        # デバイスタイプ選択
        row1 = ttk.Frame(set_frame)
        row1.pack(fill=tk.X, pady=5)
        
        ttk.Label(row1, text="デバイス:").pack(side=tk.LEFT, padx=5)
        self.device_type_var = tk.StringVar(value="X")
        device_combo = ttk.Combobox(row1, textvariable=self.device_type_var,
                                    values=["X (入力)", "Y (出力)", "M (内部リレー)", 
                                           "D (データレジスタ)", "B (リンクリレー)",
                                           "W (リンクレジスタ)", "R (ファイルレジスタ)"],
                                    state="readonly", width=18)
        device_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row1, text="番号:").pack(side=tk.LEFT, padx=5)
        self.device_addr_var = tk.StringVar(value="0")
        ttk.Entry(row1, textvariable=self.device_addr_var, width=8).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row1, text="値:").pack(side=tk.LEFT, padx=5)
        self.device_value_var = tk.StringVar(value="1")
        ttk.Entry(row1, textvariable=self.device_value_var, width=10).pack(side=tk.LEFT, padx=5)
        
        self.set_device_btn = ttk.Button(row1, text="設定", command=self._set_device, state=tk.DISABLED)
        self.set_device_btn.pack(side=tk.LEFT, padx=10)
        
        # クイック設定ボタン
        quick_frame = ttk.Frame(set_frame)
        quick_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(quick_frame, text="クイック設定:").pack(side=tk.LEFT, padx=5)
        
        for device in ["X0", "X1", "X2", "X3"]:
            btn = ttk.Button(quick_frame, text=f"{device} ON", width=8,
                            command=lambda d=device: self._quick_set(d, 1))
            btn.pack(side=tk.LEFT, padx=2)
        
        for device in ["X0", "X1", "X2", "X3"]:
            btn = ttk.Button(quick_frame, text=f"{device} OFF", width=8,
                            command=lambda d=device: self._quick_set(d, 0))
            btn.pack(side=tk.LEFT, padx=2)
        
        # デバイスモニタ
        monitor_frame = ttk.LabelFrame(parent, text="デバイスモニタ", padding="10")
        monitor_frame.pack(fill=tk.BOTH, expand=True)
        
        # モニタ範囲設定
        range_frame = ttk.Frame(monitor_frame)
        range_frame.pack(fill=tk.X, pady=5)
        
        # ビットデバイス範囲
        ttk.Label(range_frame, text="ビット:").pack(side=tk.LEFT, padx=5)
        self.bit_device_var = tk.StringVar(value="X")
        bit_combo = ttk.Combobox(range_frame, textvariable=self.bit_device_var,
                                  values=["X", "Y", "M", "B"], state="readonly", width=4)
        bit_combo.pack(side=tk.LEFT, padx=2)
        
        self.bit_start_var = tk.StringVar(value="0")
        ttk.Entry(range_frame, textvariable=self.bit_start_var, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Label(range_frame, text="〜").pack(side=tk.LEFT)
        self.bit_count_var = tk.StringVar(value="16")
        ttk.Entry(range_frame, textvariable=self.bit_count_var, width=4).pack(side=tk.LEFT, padx=2)
        ttk.Label(range_frame, text="点").pack(side=tk.LEFT, padx=(0, 15))
        
        # ワードデバイス範囲
        ttk.Label(range_frame, text="ワード:").pack(side=tk.LEFT, padx=5)
        self.word_device_var = tk.StringVar(value="D")
        word_combo = ttk.Combobox(range_frame, textvariable=self.word_device_var,
                                   values=["D", "W", "R", "TN", "CN"], state="readonly", width=4)
        word_combo.pack(side=tk.LEFT, padx=2)
        
        self.word_start_var = tk.StringVar(value="0")
        ttk.Entry(range_frame, textvariable=self.word_start_var, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Label(range_frame, text="〜").pack(side=tk.LEFT)
        self.word_count_var = tk.StringVar(value="16")
        ttk.Entry(range_frame, textvariable=self.word_count_var, width=4).pack(side=tk.LEFT, padx=2)
        ttk.Label(range_frame, text="点").pack(side=tk.LEFT, padx=(0, 15))
        
        # モニタ制御
        monitor_ctrl = ttk.Frame(monitor_frame)
        monitor_ctrl.pack(fill=tk.X, pady=5)
        
        self.monitor_start_btn = ttk.Button(monitor_ctrl, text="モニタ開始", 
                                            command=self._start_device_monitor, state=tk.DISABLED)
        self.monitor_start_btn.pack(side=tk.LEFT, padx=5)
        
        self.monitor_stop_btn = ttk.Button(monitor_ctrl, text="モニタ停止", 
                                           command=self._stop_device_monitor, state=tk.DISABLED)
        self.monitor_stop_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(monitor_ctrl, text="更新間隔(ms):").pack(side=tk.LEFT, padx=(20, 5))
        self.monitor_interval_var = tk.StringVar(value="200")
        ttk.Entry(monitor_ctrl, textvariable=self.monitor_interval_var, width=6).pack(side=tk.LEFT)
        
        # プリセットボタン
        preset_frame = ttk.Frame(monitor_frame)
        preset_frame.pack(fill=tk.X, pady=5)
        ttk.Label(preset_frame, text="プリセット:").pack(side=tk.LEFT, padx=5)
        ttk.Button(preset_frame, text="D0-15", width=8,
                   command=lambda: self._set_word_range("D", 0, 16)).pack(side=tk.LEFT, padx=2)
        ttk.Button(preset_frame, text="D100-115", width=10,
                   command=lambda: self._set_word_range("D", 100, 16)).pack(side=tk.LEFT, padx=2)
        ttk.Button(preset_frame, text="D1000-1015", width=12,
                   command=lambda: self._set_word_range("D", 1000, 16)).pack(side=tk.LEFT, padx=2)
        ttk.Button(preset_frame, text="D5000-5015", width=12,
                   command=lambda: self._set_word_range("D", 5000, 16)).pack(side=tk.LEFT, padx=2)
        ttk.Button(preset_frame, text="D6000-6015", width=12,
                   command=lambda: self._set_word_range("D", 6000, 16)).pack(side=tk.LEFT, padx=2)
        
        # デバイスツリービュー
        tree_frame = ttk.Frame(monitor_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # ビットデバイス
        bit_frame = ttk.LabelFrame(tree_frame, text="ビットデバイス", padding="5")
        bit_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        self.bit_tree = ttk.Treeview(bit_frame, columns=("Value",), show="tree headings", height=15)
        self.bit_tree.heading("#0", text="デバイス")
        self.bit_tree.heading("Value", text="値")
        self.bit_tree.column("#0", width=100)
        self.bit_tree.column("Value", width=80, anchor=tk.CENTER)
        self.bit_tree.pack(fill=tk.BOTH, expand=True)
        
        # ワードデバイス
        word_frame = ttk.LabelFrame(tree_frame, text="ワードデバイス", padding="5")
        word_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.word_tree = ttk.Treeview(word_frame, columns=("Value", "Hex"), show="tree headings", height=15)
        self.word_tree.heading("#0", text="デバイス")
        self.word_tree.heading("Value", text="10進")
        self.word_tree.heading("Hex", text="16進")
        self.word_tree.column("#0", width=100)
        self.word_tree.column("Value", width=80, anchor=tk.CENTER)
        self.word_tree.column("Hex", width=80, anchor=tk.CENTER)
        self.word_tree.pack(fill=tk.BOTH, expand=True)
    
    def _create_log_tab(self, parent):
        """ログタブ"""
        # ログテキスト
        self.log_text = scrolledtext.ScrolledText(parent, font=('Consolas', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # クリアボタン
        ttk.Button(parent, text="ログクリア", command=self._clear_log).pack(anchor=tk.E, pady=5)
    
    def _log(self, message: str):
        """ログを追加"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
    
    def _clear_log(self):
        """ログをクリア"""
        self.log_text.delete(1.0, tk.END)
    
    # === サーバー制御 ===
    
    def _start_server(self):
        """サーバーを起動"""
        try:
            host = self.host_var.get()
            port = int(self.port_var.get())
            
            series_str = self.series_var.get()
            self.series = PLCSeries.Q_SERIES if "Q" in series_str else PLCSeries.IQR_SERIES
            
            self.server = MockPLCServer(host, port, self.series)
            self.server.on_log = self._log
            self.server.on_client_connected = self._on_client_connected
            self.server.on_client_disconnected = self._on_client_disconnected
            self.server.on_state_changed = self._on_state_changed
            
            if self.server.start():
                self._on_server_started()
                self._log(f"サーバー起動: {host}:{port} ({series_str})")
            else:
                messagebox.showerror("エラー", "サーバー起動に失敗しました")
                
        except Exception as e:
            messagebox.showerror("エラー", f"サーバー起動エラー: {e}")
    
    def _stop_server(self):
        """サーバーを停止"""
        self._stop_device_monitor()
        
        if self.server:
            self.server.stop()
            self.server = None
        
        self._on_server_stopped()
        self._log("サーバー停止")
    
    def _on_server_started(self):
        """サーバー起動時"""
        self.start_btn['state'] = tk.DISABLED
        self.stop_btn['state'] = tk.NORMAL
        self.run_btn['state'] = tk.NORMAL
        self.stop_plc_btn['state'] = tk.NORMAL
        self.reset_btn['state'] = tk.NORMAL
        self.load_sample_btn['state'] = tk.NORMAL
        self.load_file_btn['state'] = tk.NORMAL
        self.compile_btn['state'] = tk.NORMAL
        self.clear_ladder_btn['state'] = tk.NORMAL
        self.set_device_btn['state'] = tk.NORMAL
        self.monitor_start_btn['state'] = tk.NORMAL
        
        self.server_status.config(text="起動中", foreground="green")
        self.plc_status.config(text="STOP", foreground="orange")
    
    def _on_server_stopped(self):
        """サーバー停止時"""
        self.start_btn['state'] = tk.NORMAL
        self.stop_btn['state'] = tk.DISABLED
        self.run_btn['state'] = tk.DISABLED
        self.stop_plc_btn['state'] = tk.DISABLED
        self.reset_btn['state'] = tk.DISABLED
        self.load_sample_btn['state'] = tk.DISABLED
        self.load_file_btn['state'] = tk.DISABLED
        self.compile_btn['state'] = tk.DISABLED
        self.clear_ladder_btn['state'] = tk.DISABLED
        self.set_device_btn['state'] = tk.DISABLED
        self.monitor_start_btn['state'] = tk.DISABLED
        self.monitor_stop_btn['state'] = tk.DISABLED
        
        self.server_status.config(text="停止", foreground="red")
        self.plc_status.config(text="-", foreground="gray")
        self.client_status.config(text="未接続", foreground="gray")
    
    def _on_client_connected(self, host: str, port: int):
        """クライアント接続時"""
        self.root.after(0, lambda: self.client_status.config(
            text=f"接続中 ({host}:{port})", foreground="green"))
    
    def _on_client_disconnected(self):
        """クライアント切断時"""
        self.root.after(0, lambda: self.client_status.config(
            text="未接続", foreground="gray"))
    
    def _on_state_changed(self, state: PLCState):
        """PLC状態変更時"""
        color = "green" if state == PLCState.RUN else "orange"
        self.root.after(0, lambda: self.plc_status.config(text=state.value, foreground=color))
    
    # === PLC制御 ===
    
    def _plc_run(self):
        """PLC RUN"""
        if self.server:
            self.server.state = PLCState.RUN
            self.server.ladder_engine.start()
            self.plc_status.config(text="RUN", foreground="green")
            self._log("PLC RUN")
    
    def _plc_stop(self):
        """PLC STOP"""
        if self.server:
            self.server.state = PLCState.STOP
            self.server.ladder_engine.stop()
            self.plc_status.config(text="STOP", foreground="orange")
            self._log("PLC STOP")
    
    def _plc_reset(self):
        """PLC RESET"""
        if self.server:
            self.server.state = PLCState.STOP
            self.server.ladder_engine.stop()
            self.server.ladder_engine.reset_all()
            self.server.devices.clear_all()
            self.plc_status.config(text="STOP", foreground="orange")
            self._log("PLC RESET")
    
    # === ラダープログラム ===
    
    def _load_sample(self):
        """サンプルプログラムをロード"""
        if not self.server:
            return
        
        name = self.sample_var.get()
        ladder = None
        
        if name == "自己保持回路":
            ladder = create_gx_sample_1()
        elif name == "タイマ回路":
            ladder = create_gx_sample_2()
        elif name == "カウンタ回路":
            ladder = create_gx_sample_3()
        elif name == "データ演算":
            ladder = create_gx_sample_4()
        elif name == "複雑条件":
            ladder = create_gx_sample_5()
        
        if ladder:
            self.server.clear_ladder_programs()
            self.server.load_ladder_program(ladder.get_program())
            self.current_program_var.set(f"ロード済み: {name}")
            self._log(f"サンプルプログラムロード: {name}")
    
    def _browse_file(self):
        """ファイル参照"""
        filepath = filedialog.askopenfilename(
            title="ラダーファイルを選択",
            filetypes=[("テキストファイル", "*.txt"), ("すべてのファイル", "*.*")]
        )
        if filepath:
            self.file_path_var.set(filepath)
    
    def _load_file(self):
        """ファイルからロード"""
        if not self.server:
            return
        
        filepath = self.file_path_var.get()
        if not filepath or not os.path.exists(filepath):
            messagebox.showerror("エラー", "ファイルが見つかりません")
            return
        
        loader = GXProjectLoader()
        ladder = loader.load_from_file(filepath)
        
        if ladder:
            self.server.clear_ladder_programs()
            self.server.load_ladder_program(ladder.get_program())
            self.current_program_var.set(f"ロード済み: {os.path.basename(filepath)}")
            self._log(f"ファイルロード: {filepath}")
            
            if loader.warnings:
                for warning in loader.warnings:
                    self._log(f"警告: {warning}")
        else:
            for error in loader.errors:
                self._log(f"エラー: {error}")
            messagebox.showerror("エラー", "ファイルの読み込みに失敗しました")
    
    def _compile_ladder(self):
        """エディタのラダーをコンパイル＆ロード"""
        if not self.server:
            return
        
        text = self.ladder_editor.get(1.0, tk.END)
        
        loader = GXProjectLoader()
        ladder = loader.load_from_text(text, "Editor Program")
        
        if ladder:
            self.server.clear_ladder_programs()
            self.server.load_ladder_program(ladder.get_program())
            self.current_program_var.set("ロード済み: エディタプログラム")
            self._log("エディタプログラムをコンパイル＆ロード")
            
            if loader.warnings:
                for warning in loader.warnings:
                    self._log(f"警告: {warning}")
        else:
            for error in loader.errors:
                self._log(f"エラー: {error}")
            messagebox.showerror("コンパイルエラー", "\n".join(loader.errors))
    
    def _clear_ladder(self):
        """ラダープログラムをクリア"""
        if self.server:
            self.server.clear_ladder_programs()
            self.current_program_var.set("なし")
            self._log("ラダープログラムクリア")
    
    def _insert_sample(self):
        """サンプルを挿入"""
        self.ladder_editor.delete(1.0, tk.END)
        self.ladder_editor.insert(tk.END, SAMPLE_LADDER_TEXT)
    
    # === デバイス操作 ===
    
    def _set_device(self):
        """デバイスを設定"""
        if not self.server:
            return
        
        try:
            device_str = self.device_type_var.get().split()[0]  # "X (入力)" -> "X"
            address = int(self.device_addr_var.get(), 16 if device_str in ['X', 'Y', 'B', 'W'] else 10)
            value = int(self.device_value_var.get())
            
            self.server.set_device_value(device_str, address, value)
            self._log(f"デバイス設定: {device_str}{address} = {value}")
            
        except Exception as e:
            messagebox.showerror("エラー", f"設定エラー: {e}")
    
    def _quick_set(self, device: str, value: int):
        """クイック設定"""
        if not self.server:
            return
        
        device_type = device[0]
        address = int(device[1:], 16 if device_type in ['X', 'Y', 'B', 'W'] else 10)
        
        self.server.set_device_value(device_type, address, value)
        self._log(f"クイック設定: {device} = {value}")
    
    def _set_word_range(self, device: str, start: int, count: int):
        """ワードデバイスの表示範囲を設定"""
        self.word_device_var.set(device)
        self.word_start_var.set(str(start))
        self.word_count_var.set(str(count))
    
    # === デバイスモニタ ===
    
    def _start_device_monitor(self):
        """デバイスモニタを開始"""
        if self.device_monitor_running:
            return
        
        self.device_monitor_running = True
        self.monitor_start_btn['state'] = tk.DISABLED
        self.monitor_stop_btn['state'] = tk.NORMAL
        
        self.device_monitor_thread = threading.Thread(target=self._device_monitor_loop, daemon=True)
        self.device_monitor_thread.start()
    
    def _stop_device_monitor(self):
        """デバイスモニタを停止"""
        self.device_monitor_running = False
        
        if self.device_monitor_thread:
            self.device_monitor_thread.join(timeout=1.0)
            self.device_monitor_thread = None
        
        if self.server:
            self.monitor_start_btn['state'] = tk.NORMAL
        self.monitor_stop_btn['state'] = tk.DISABLED
    
    def _device_monitor_loop(self):
        """デバイスモニタループ"""
        while self.device_monitor_running and self.server:
            try:
                interval = int(self.monitor_interval_var.get())
            except:
                interval = 200
            
            try:
                # ビットデバイス範囲を取得
                bit_device = self.bit_device_var.get()
                bit_device_type = DeviceType.from_code(bit_device)
                is_hex_bit = bit_device in ['X', 'Y', 'B']
                try:
                    bit_start = int(self.bit_start_var.get(), 16 if is_hex_bit else 10)
                except:
                    bit_start = 0
                try:
                    bit_count = int(self.bit_count_var.get())
                except:
                    bit_count = 16
                bit_count = min(bit_count, 64)  # 最大64点
                
                # ビットデバイス取得
                bit_data = {}
                if bit_device_type:
                    for i in range(bit_count):
                        addr = bit_start + i
                        val = self.server.devices.get_bit(bit_device_type, addr)
                        if is_hex_bit:
                            bit_data[f"{bit_device}{addr:X}"] = 1 if val else 0
                        else:
                            bit_data[f"{bit_device}{addr}"] = 1 if val else 0
                
                # ワードデバイス範囲を取得
                word_device = self.word_device_var.get()
                word_device_type = DeviceType.from_code(word_device)
                is_hex_word = word_device in ['W']
                try:
                    word_start = int(self.word_start_var.get(), 16 if is_hex_word else 10)
                except:
                    word_start = 0
                try:
                    word_count = int(self.word_count_var.get())
                except:
                    word_count = 16
                word_count = min(word_count, 64)  # 最大64点
                
                # ワードデバイス取得
                word_data = {}
                if word_device_type:
                    for i in range(word_count):
                        addr = word_start + i
                        val = self.server.devices.get_word(word_device_type, addr)
                        if is_hex_word:
                            word_data[f"{word_device}{addr:X}"] = val
                        else:
                            word_data[f"{word_device}{addr}"] = val
                
                # UI更新
                self.root.after(0, lambda b=bit_data, w=word_data: self._update_device_trees(b, w))
                
            except Exception as e:
                pass
            
            time.sleep(interval / 1000.0)
    
    def _update_device_trees(self, bit_data: Dict, word_data: Dict):
        """デバイスツリーを更新"""
        # ビットツリー更新
        for item in self.bit_tree.get_children():
            self.bit_tree.delete(item)
        
        for device, value in bit_data.items():
            tag = "on" if value else "off"
            self.bit_tree.insert("", tk.END, text=device, values=(value,), tags=(tag,))
        
        self.bit_tree.tag_configure("on", background="#90EE90")
        self.bit_tree.tag_configure("off", background="white")
        
        # ワードツリー更新
        for item in self.word_tree.get_children():
            self.word_tree.delete(item)
        
        for device, value in word_data.items():
            self.word_tree.insert("", tk.END, text=device, values=(value, f"{value:04X}"))
    
    def _on_closing(self):
        """ウィンドウを閉じる時"""
        self._stop_device_monitor()
        
        if self.server:
            self.server.stop()
        
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
    
    app = PLCServerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
