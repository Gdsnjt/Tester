"""
GigEカメラクライアントGUI
Harvester/モックカメラ両対応
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
from datetime import datetime
import threading
import queue
import time
import numpy as np
import cv2
import os

# プロジェクト内モジュール
from camera_interface import ICameraProvider, CameraState, ImageData, get_provider


class CameraGUI:
    """
    カメラ制御GUIアプリケーション
    
    モード:
    - Harvester: 実カメラ接続 (ProducerGEV.cti必須)
    - Mock: テスト用シミュレーション
    """
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("GigE Camera Client")
        self.root.geometry("1100x850")
        
        # カメラプロバイダー
        self.provider: ICameraProvider = None
        self.current_mode = "mock"  # "mock" or "harvester"
        
        # 表示モード
        self.display_mode = "live"  # "live" or "single"
        
        # 画像表示用
        self.frame_count = 0
        self.current_image: np.ndarray = None
        self.is_capturing = False  # 撮影中フラグ
        
        # ライブビュー用
        self.image_queue = queue.Queue(maxsize=3)
        self.acquisition_thread = None
        self.display_running = False
        
        # FPS計算用
        self.fps_start_time = 0.0
        self.fps_frame_count = 0
        self.current_fps = 0.0
        
        # FPS計算用
        self.fps_start_time = 0.0
        self.fps_frame_count = 0
        self.current_fps = 0.0
        
        # UI作成
        self._create_widgets()
        
        # 初期モードで初期化
        self._switch_mode(self.current_mode)
        
        # ウィンドウを閉じる時の処理
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
    
    def _create_widgets(self):
        """UIウィジェットを作成"""
        # メインコンテナ
        main_container = ttk.Frame(self.root, padding="10")
        main_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # ウィンドウのリサイズ設定
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_container.columnconfigure(1, weight=1)
        main_container.rowconfigure(1, weight=1)
        
        # === 左側パネル（コントロール） ===
        control_frame = ttk.LabelFrame(main_container, text="コントロール", padding="10")
        control_frame.grid(row=0, column=0, rowspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))
        
        self._create_mode_section(control_frame)
        self._create_connection_section(control_frame)
        self._create_acquisition_section(control_frame)
        self._create_parameter_section(control_frame)
        self._create_info_section(control_frame)
        
        # === 右側パネル（画像表示） ===
        image_frame = ttk.LabelFrame(main_container, text="画像表示", padding="10")
        image_frame.grid(row=0, column=1, rowspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        image_frame.columnconfigure(0, weight=1)
        image_frame.rowconfigure(0, weight=1)
        
        # Canvas
        self.canvas = tk.Canvas(image_frame, bg='#1a1a1a')
        self.canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 画像情報
        info_frame = ttk.Frame(image_frame)
        info_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(5, 0))
        
        self.frame_label = ttk.Label(info_frame, text="フレーム: 0")
        self.frame_label.grid(row=0, column=0, sticky=tk.W)
        
        self.fps_label = ttk.Label(info_frame, text="FPS: 0.0")
        self.fps_label.grid(row=0, column=1, padx=(20, 0), sticky=tk.W)
        
        self.resolution_label = ttk.Label(info_frame, text="解像度: -")
        self.resolution_label.grid(row=0, column=2, padx=(20, 0), sticky=tk.W)
        
        # ステータスバー
        self.status_var = tk.StringVar(value="準備完了")
        status_bar = ttk.Label(main_container, textvariable=self.status_var, 
                              relief=tk.SUNKEN, anchor=tk.W)
        status_bar.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        
        # 初期表示モード設定
        self._switch_display_mode()
    
    def _create_mode_section(self, parent):
        """モード選択セクション"""
        row = 0
        
        # モード選択
        mode_frame = ttk.LabelFrame(parent, text="1. モード選択", padding="10")
        mode_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.mode_var = tk.StringVar(value="mock")
        
        mock_rb = ttk.Radiobutton(mode_frame, text="モック (テスト用)", 
                                  variable=self.mode_var, value="mock",
                                  command=lambda: self._switch_mode("mock"))
        mock_rb.grid(row=0, column=0, sticky=tk.W, padx=5)
        
        harvester_rb = ttk.Radiobutton(mode_frame, text="Harvester (実カメラ)", 
                                       variable=self.mode_var, value="harvester",
                                       command=lambda: self._switch_mode("harvester"))
        harvester_rb.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        # モード説明
        self.mode_info_label = ttk.Label(mode_frame, text="", foreground="gray")
        self.mode_info_label.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))
        
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=row+1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
    
    def _create_connection_section(self, parent):
        """接続セクション"""
        row = 2
        
        conn_frame = ttk.LabelFrame(parent, text="2. デバイス接続", padding="10")
        conn_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # デバイス検出
        ttk.Button(conn_frame, text="デバイス検出", 
                  command=self._discover_devices).grid(row=0, column=0, columnspan=2, pady=5)
        
        # デバイス選択
        ttk.Label(conn_frame, text="デバイス:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.device_combo = ttk.Combobox(conn_frame, state="readonly", width=35)
        self.device_combo.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # 接続ボタン
        btn_frame = ttk.Frame(conn_frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=10)
        
        self.connect_btn = ttk.Button(btn_frame, text="接続", 
                                      command=self._connect, state=tk.DISABLED)
        self.connect_btn.grid(row=0, column=0, padx=5)
        
        self.disconnect_btn = ttk.Button(btn_frame, text="切断", 
                                         command=self._disconnect, state=tk.DISABLED)
        self.disconnect_btn.grid(row=0, column=1, padx=5)
        
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=row+1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
    
    def _create_acquisition_section(self, parent):
        """撮影・表示セクション"""
        row = 4
        
        acq_frame = ttk.LabelFrame(parent, text="3. 撮影・表示", padding="10")
        acq_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # 表示モード選択
        mode_frame = ttk.Frame(acq_frame)
        mode_frame.grid(row=0, column=0, columnspan=2, pady=5)
        
        ttk.Label(mode_frame, text="表示モード:").grid(row=0, column=0, sticky=tk.W)
        
        self.display_mode_var = tk.StringVar(value="live")
        
        live_rb = ttk.Radiobutton(mode_frame, text="ライブビュー", 
                                 variable=self.display_mode_var, value="live",
                                 command=self._switch_display_mode)
        live_rb.grid(row=0, column=1, padx=10, sticky=tk.W)
        
        single_rb = ttk.Radiobutton(mode_frame, text="単発撮影", 
                                   variable=self.display_mode_var, value="single",
                                   command=self._switch_display_mode)
        single_rb.grid(row=0, column=2, padx=10, sticky=tk.W)
        
        # ライブビュー用ボタン
        self.live_frame = ttk.Frame(acq_frame)
        self.live_frame.grid(row=1, column=0, columnspan=2, pady=10)
        
        self.start_btn = ttk.Button(self.live_frame, text="▶ ライブ開始", 
                                    command=self._start_live_view, state=tk.DISABLED)
        self.start_btn.grid(row=0, column=0, padx=5)
        
        self.stop_btn = ttk.Button(self.live_frame, text="⏹ ライブ停止", 
                                   command=self._stop_live_view, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=1, padx=5)
        
        # 単発撮影用ボタン
        self.single_frame = ttk.Frame(acq_frame)
        self.single_frame.grid(row=2, column=0, columnspan=2, pady=10)
        
        self.capture_btn = ttk.Button(self.single_frame, text="📷 撮影", 
                                     command=self._capture_image, state=tk.DISABLED,
                                     width=15)
        self.capture_btn.grid(row=0, column=0, pady=5)
        
        # 保存ボタン（共通）
        self.save_btn = ttk.Button(acq_frame, text="画像を保存", 
                                   command=self._save_image, state=tk.DISABLED)
        self.save_btn.grid(row=3, column=0, columnspan=2, pady=10)
        
        # 初期状態設定
        # self._switch_display_mode()  # ステータスバー作成後に移動
        
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=row+1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
    
    def _create_parameter_section(self, parent):
        """パラメータセクション"""
        row = 6
        
        param_frame = ttk.LabelFrame(parent, text="カメラパラメータ", padding="10")
        param_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # 露光時間
        ttk.Label(param_frame, text="露光時間 (μs):").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.exposure_var = tk.StringVar(value="10000")
        self.exposure_entry = ttk.Entry(param_frame, textvariable=self.exposure_var, width=12)
        self.exposure_entry.grid(row=0, column=1, sticky=tk.W, pady=5)
        self.exposure_btn = ttk.Button(param_frame, text="設定", 
                                       command=self._set_exposure, state=tk.DISABLED, width=6)
        self.exposure_btn.grid(row=0, column=2, padx=5)
        
        # ゲイン
        ttk.Label(param_frame, text="ゲイン (dB):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.gain_var = tk.StringVar(value="0.0")
        self.gain_entry = ttk.Entry(param_frame, textvariable=self.gain_var, width=12)
        self.gain_entry.grid(row=1, column=1, sticky=tk.W, pady=5)
        self.gain_btn = ttk.Button(param_frame, text="設定", 
                                   command=self._set_gain, state=tk.DISABLED, width=6)
        self.gain_btn.grid(row=1, column=2, padx=5)
        
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=row+1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
    
    def _create_info_section(self, parent):
        """情報セクション"""
        row = 8
        
        ttk.Label(parent, text="カメラ情報", font=('', 10, 'bold')).grid(
            row=row, column=0, columnspan=3, sticky=tk.W)
        
        self.info_text = tk.Text(parent, height=8, width=38, state=tk.DISABLED,
                                 bg='#f5f5f5', relief=tk.FLAT)
        self.info_text.grid(row=row+1, column=0, columnspan=3, pady=5, sticky=(tk.W, tk.E))
    
    # === モード切替 ===
    
    def _switch_mode(self, mode: str):
        """モードを切り替え"""
        # 既存接続を切断
        if self.provider and self.provider.is_connected:
            self._disconnect()
        
        if self.provider:
            self.provider.cleanup()
        
        self.current_mode = mode
        
        try:
            if mode == "mock":
                from mock_camera import MockCameraProvider
                self.provider = MockCameraProvider()
                self.provider.initialize()
                self.mode_info_label.config(text="テスト用モック。実カメラ不要。")
                self.root.title("GigE Camera Client - Mock Mode")
            else:
                from harvester_camera import HarvesterCameraProvider
                self.provider = HarvesterCameraProvider()
                
                # CTIファイルチェック
                project_dir = os.path.dirname(os.path.abspath(__file__))
                cti_file = os.path.join(project_dir, "ProducerGEV.cti")
                
                if os.path.exists(cti_file):
                    if self.provider.initialize(cti_file=cti_file):
                        self.mode_info_label.config(text=f"CTI: {os.path.basename(cti_file)}")
                    else:
                        self.mode_info_label.config(text="CTI初期化失敗", foreground="red")
                else:
                    self.mode_info_label.config(text="ProducerGEV.cti が必要です", foreground="red")
                
                self.root.title("GigE Camera Client - Harvester Mode")
            
            self._update_status(f"モード切替: {mode}")
            
        except Exception as e:
            messagebox.showerror("エラー", f"モード切替エラー:\n{str(e)}")
            self._update_status(f"モード切替エラー: {e}")
    
    # === デバイス操作 ===
    
    def _discover_devices(self):
        """デバイスを検出"""
        if self.provider is None:
            return
        
        self._update_status("デバイス検出中...")
        self.root.update()
        
        try:
            devices = self.provider.discover_devices()
            
            device_list = [str(dev) for dev in devices]
            self.device_combo['values'] = device_list
            
            if device_list:
                self.device_combo.current(0)
                self.connect_btn['state'] = tk.NORMAL
                self._update_status(f"{len(device_list)}台のデバイスを検出")
            else:
                self.device_combo.set('')
                self.connect_btn['state'] = tk.DISABLED
                self._update_status("デバイスが見つかりません")
                
        except Exception as e:
            messagebox.showerror("エラー", f"デバイス検出エラー:\n{str(e)}")
            self._update_status(f"検出エラー: {e}")
    
    def _connect(self):
        """カメラに接続"""
        if self.provider is None:
            return
        
        device_index = self.device_combo.current()
        if device_index < 0:
            messagebox.showwarning("警告", "デバイスを選択してください")
            return
        
        self._update_status("接続中...")
        self.root.update()
        
        try:
            if self.provider.connect(device_index):
                self._on_connected()
            else:
                messagebox.showerror("エラー", "接続に失敗しました")
                self._update_status("接続失敗")
                
        except Exception as e:
            messagebox.showerror("エラー", f"接続エラー:\n{str(e)}")
            self._update_status(f"接続エラー: {e}")
    
    def _disconnect(self):
        """カメラから切断"""
        if self.provider is None:
            return
        
        try:
            # ライブビューを停止
            if self.display_running:
                self._stop_live_view()
            
            self.provider.disconnect()
            self._on_disconnected()
            
        except Exception as e:
            messagebox.showerror("エラー", f"切断エラー:\n{str(e)}")
    
    def _on_connected(self):
        """接続時の処理"""
        self.connect_btn['state'] = tk.DISABLED
        self.disconnect_btn['state'] = tk.NORMAL
        self.exposure_btn['state'] = tk.NORMAL
        self.gain_btn['state'] = tk.NORMAL
        
        # 表示モードに応じてボタンを有効化
        self._update_button_states()
        
        # パラメータ表示
        params = self.provider.parameters
        self.exposure_var.set(f"{params.exposure_time:.0f}")
        self.gain_var.set(f"{params.gain:.1f}")
        
        # 情報表示
        self._update_camera_info()
        
        device = self.provider.current_device
        self._update_status(f"接続: {device.model if device else 'Unknown'}")
    
    def _on_disconnected(self):
        """切断時の処理"""
        self.connect_btn['state'] = tk.NORMAL
        self.disconnect_btn['state'] = tk.DISABLED
        self.start_btn['state'] = tk.DISABLED
        self.stop_btn['state'] = tk.DISABLED
        self.capture_btn['state'] = tk.DISABLED
        self.save_btn['state'] = tk.DISABLED
        self.exposure_btn['state'] = tk.DISABLED
        self.gain_btn['state'] = tk.DISABLED
        
        # 情報クリア
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        self.info_text.config(state=tk.DISABLED)
        
        self._update_status("切断完了")
    
    # === 表示モード切替 ===
    
    def _switch_display_mode(self):
        """表示モードを切り替え"""
        # 現在のライブビューを停止
        if self.display_running:
            self._stop_live_view()
        
        self.display_mode = self.display_mode_var.get()
        
        if self.display_mode == "live":
            # ライブビューモード
            self.live_frame.grid()
            self.single_frame.grid_remove()
            self._update_status("モード: ライブビュー")
        else:
            # 単発撮影モード
            self.live_frame.grid_remove()
            self.single_frame.grid()
            self._update_status("モード: 単発撮影")
        
        # ボタン状態を更新
        self._update_button_states()
    
    def _update_button_states(self):
        """表示モードとカメラ状態に応じてボタン状態を更新"""
        if not self.provider or not self.provider.is_connected:
            return
        
        if self.display_mode == "live":
            self.start_btn['state'] = tk.NORMAL if not self.display_running else tk.DISABLED
            self.stop_btn['state'] = tk.NORMAL if self.display_running else tk.DISABLED
            self.capture_btn['state'] = tk.DISABLED
        else:
            self.start_btn['state'] = tk.DISABLED
            self.stop_btn['state'] = tk.DISABLED
            self.capture_btn['state'] = tk.NORMAL
    
    # === ライブビュー ===
    
    def _start_live_view(self):
        """ライブビューを開始"""
        if self.provider is None or not self.provider.is_connected:
            return
        
        try:
            # すでに取得中でない場合のみ開始
            if not self.provider.is_acquiring:
                if not self.provider.start_acquisition():
                    messagebox.showerror("エラー", "ライブビュー開始に失敗しました")
                    return
            
            self.display_running = True
            self.fps_frame_count = 0
            self.fps_start_time = 0
            
            # 取得スレッド開始
            self.acquisition_thread = threading.Thread(
                target=self._acquisition_loop, daemon=True)
            self.acquisition_thread.start()
            
            # 表示更新開始
            self._update_live_display()
            
            self._update_status("ライブビュー中...")
            self._update_button_states()
                
        except Exception as e:
            messagebox.showerror("エラー", f"ライブビュー開始エラー:\n{str(e)}")
    
    def _stop_live_view(self):
        """ライブビューを停止"""
        if self.provider is None:
            return
        
        try:
            self.display_running = False
            
            if self.acquisition_thread:
                self.acquisition_thread.join(timeout=2.0)
                self.acquisition_thread = None
            
            if self.provider.is_acquiring:
                self.provider.stop_acquisition()
            
            # キューをクリア
            while not self.image_queue.empty():
                try:
                    self.image_queue.get_nowait()
                except queue.Empty:
                    break
            
            self._update_status("ライブビュー停止")
            self._update_button_states()
            
        except Exception as e:
            messagebox.showerror("エラー", f"停止エラー:\n{str(e)}")
    
    def _acquisition_loop(self):
        """画像取得ループ（別スレッド）"""
        while self.display_running and self.provider and self.provider.is_acquiring:
            try:
                image_data = self.provider.get_image(timeout=1.0)
                
                if image_data is not None:
                    # キューがいっぱいなら古いのを捨てる
                    if self.image_queue.full():
                        try:
                            self.image_queue.get_nowait()
                        except queue.Empty:
                            pass
                    
                    self.image_queue.put(image_data)
                    self.frame_count += 1
                    
            except Exception as e:
                if self.display_running:
                    print(f"取得エラー: {e}")
                break
    
    def _update_live_display(self):
        """ライブビュー表示を更新"""
        if not self.display_running:
            return
        
        try:
            image_data = self.image_queue.get_nowait()
            
            # 画像を保存（保存用）
            self.current_image = image_data.data.copy()
            
            # 画像を表示
            self._display_image(image_data)
            
            # 保存ボタンを有効化
            self.save_btn['state'] = tk.NORMAL
            
            # FPS計算
            self.fps_frame_count += 1
            current_time = time.time()
            if self.fps_start_time == 0:
                self.fps_start_time = current_time
            elif current_time - self.fps_start_time >= 1.0:
                self.current_fps = self.fps_frame_count / (current_time - self.fps_start_time)
                self.fps_label.config(text=f"FPS: {self.current_fps:.1f}")
                self.fps_frame_count = 0
                self.fps_start_time = current_time
                
        except queue.Empty:
            pass
        
        # 次の更新をスケジュール
        if self.display_running:
            self.root.after(16, self._update_live_display)  # 約60fps
    
    def _capture_image(self):
        """画像を1枚撮影"""
        if self.provider is None or not self.provider.is_connected:
            return
        
        if self.is_capturing:
            return  # 撮影中の場合はスキップ
        
        self.is_capturing = True
        self.capture_btn['state'] = tk.DISABLED
        self._update_status("撮影中...")
        
        # UIを更新してボタンの無効化を反映
        self.root.update()
        
        try:
            # プロバイダーが取得状態でない場合は開始
            if not self.provider.is_acquiring:
                if not self.provider.start_acquisition():
                    messagebox.showerror("エラー", "撮影準備に失敗しました")
                    self.is_capturing = False
                    self.capture_btn['state'] = tk.NORMAL
                    return
            
            # 画像を取得
            image_data = self.provider.get_image(timeout=2.0)
            
            if image_data is not None:
                self.frame_count += 1
                self.current_image = image_data.data.copy()
                
                # 画像を表示
                self._display_image(image_data)
                
                # FPS表示をクリア（単発撮影では不要）
                self.fps_label.config(text="FPS: -")
                
                # 保存ボタンを有効化
                self.save_btn['state'] = tk.NORMAL
                
                self._update_status(f"撮影完了 (フレーム: {self.frame_count})")
            else:
                messagebox.showerror("エラー", "画像の取得に失敗しました")
                self._update_status("撮影失敗")
                
        except Exception as e:
            messagebox.showerror("エラー", f"撮影エラー:\n{str(e)}")
            self._update_status(f"撮影エラー: {e}")
        
        finally:
            self.is_capturing = False
            self.capture_btn['state'] = tk.NORMAL
            # 注: 単発撮影後も取得状態を維持（ライブビューへのスムーズな遷移のため）
    
    def _display_image(self, image_data: ImageData):
        """画像をCanvasに表示"""
        try:
            # OpenCVからPIL形式に変換
            if len(image_data.data.shape) == 2:
                image_rgb = cv2.cvtColor(image_data.data, cv2.COLOR_GRAY2RGB)
            else:
                image_rgb = cv2.cvtColor(image_data.data, cv2.COLOR_BGR2RGB)
            
            # PILイメージに変換
            pil_image = Image.fromarray(image_rgb)
            
            # Canvasサイズに合わせてリサイズ
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            if canvas_width > 1 and canvas_height > 1:
                img_ratio = pil_image.width / pil_image.height
                canvas_ratio = canvas_width / canvas_height
                
                if img_ratio > canvas_ratio:
                    new_width = canvas_width
                    new_height = int(canvas_width / img_ratio)
                else:
                    new_height = canvas_height
                    new_width = int(canvas_height * img_ratio)
                
                pil_image = pil_image.resize((new_width, new_height), Image.LANCZOS)
            
            # 表示
            self.photo = ImageTk.PhotoImage(pil_image)
            self.canvas.delete("all")
            self.canvas.create_image(
                canvas_width // 2, canvas_height // 2,
                anchor=tk.CENTER, image=self.photo
            )
            
            # 情報更新
            self.frame_label.config(text=f"フレーム: {self.frame_count}")
            self.resolution_label.config(text=f"解像度: {image_data.width}x{image_data.height}")
                
        except Exception as e:
            print(f"画像表示エラー: {e}")
    
    # === パラメータ設定 ===
    
    def _set_exposure(self):
        """露光時間を設定"""
        if self.provider is None or not self.provider.is_connected:
            return
        
        try:
            value = float(self.exposure_var.get())
            if self.provider.set_exposure_time(value):
                self._update_status(f"露光時間: {value} μs")
                self._update_camera_info()
            else:
                messagebox.showerror("エラー", "露光時間の設定に失敗しました")
        except ValueError:
            messagebox.showerror("エラー", "有効な数値を入力してください")
    
    def _set_gain(self):
        """ゲインを設定"""
        if self.provider is None or not self.provider.is_connected:
            return
        
        try:
            value = float(self.gain_var.get())
            if self.provider.set_gain(value):
                self._update_status(f"ゲイン: {value} dB")
                self._update_camera_info()
            else:
                messagebox.showerror("エラー", "ゲインの設定に失敗しました")
        except ValueError:
            messagebox.showerror("エラー", "有効な数値を入力してください")
    
    # === 画像保存 ===
    
    def _save_image(self):
        """現在の画像を保存"""
        if self.current_image is None:
            messagebox.showwarning("警告", "保存する画像がありません")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"capture_{timestamp}.png"
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".png",
            initialfile=default_filename,
            filetypes=[
                ("PNG files", "*.png"),
                ("JPEG files", "*.jpg"),
                ("TIFF files", "*.tiff"),
                ("All files", "*.*")
            ]
        )
        
        if filename:
            try:
                cv2.imwrite(filename, self.current_image)
                self._update_status(f"保存: {os.path.basename(filename)}")
            except Exception as e:
                messagebox.showerror("エラー", f"保存エラー:\n{str(e)}")
    
    # === 情報表示 ===
    
    def _update_camera_info(self):
        """カメラ情報を更新"""
        if self.provider is None:
            return
        
        device = self.provider.current_device
        params = self.provider.parameters
        
        info_lines = []
        info_lines.append(f"=== カメラ情報 ===")
        
        if device:
            info_lines.append(f"ベンダー: {device.vendor}")
            info_lines.append(f"モデル: {device.model}")
            info_lines.append(f"シリアル: {device.serial_number}")
        
        info_lines.append(f"")
        info_lines.append(f"=== パラメータ ===")
        info_lines.append(f"解像度: {params.width} x {params.height}")
        info_lines.append(f"ピクセル形式: {params.pixel_format}")
        info_lines.append(f"露光時間: {params.exposure_time:.1f} μs")
        info_lines.append(f"ゲイン: {params.gain:.1f} dB")
        
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(1.0, "\n".join(info_lines))
        self.info_text.config(state=tk.DISABLED)
    
    def _update_status(self, message: str):
        """ステータスを更新"""
        mode_str = "Mock" if self.current_mode == "mock" else "Harvester"
        self.status_var.set(f"[{mode_str}] {message}")
    
    # === クリーンアップ ===
    
    def _on_closing(self):
        """ウィンドウを閉じる時"""
        # ライブビューを停止
        if self.display_running:
            self._stop_live_view()
            
        if self.provider:
            self.provider.cleanup()
        
        self.root.destroy()


def main():
    """メイン関数"""
    root = tk.Tk()
    
    # テーマ設定（利用可能な場合）
    try:
        style = ttk.Style()
        if 'clam' in style.theme_names():
            style.theme_use('clam')
    except:
        pass
    
    app = CameraGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
