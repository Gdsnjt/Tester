"""
GigE Visionモックカメラサーバー GUI
サーバー起動・設定・画像プレビューを提供
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import time
import os
from typing import Optional
import numpy as np
import cv2
from PIL import Image, ImageTk

from gige_mock_server import GigEMockCameraServer, MockCameraConfig
from gige_protocol import PixelFormat


class MockCameraServerGUI:
    """モックカメラサーバーGUI"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("GigE Vision モックカメラサーバー")
        self.root.geometry("900x700")
        
        # サーバー
        self.server: Optional[GigEMockCameraServer] = None
        
        # プレビュー
        self._preview_running = False
        self._preview_thread: Optional[threading.Thread] = None
        self._current_image: Optional[np.ndarray] = None
        
        # ログ
        self._log_buffer = []
        
        self._create_widgets()
        self._update_status()
    
    def _create_widgets(self):
        """ウィジェット作成"""
        # メインフレーム
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 左側: 設定パネル
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        
        # カメラ設定
        settings_frame = ttk.LabelFrame(left_frame, text="カメラ設定", padding=10)
        settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        # ベンダー
        ttk.Label(settings_frame, text="ベンダー:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.vendor_var = tk.StringVar(value="MockCam Corp")
        ttk.Entry(settings_frame, textvariable=self.vendor_var, width=25).grid(row=0, column=1, pady=2)
        
        # モデル
        ttk.Label(settings_frame, text="モデル:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.model_var = tk.StringVar(value="GigE-Mock-1000")
        ttk.Entry(settings_frame, textvariable=self.model_var, width=25).grid(row=1, column=1, pady=2)
        
        # シリアル番号
        ttk.Label(settings_frame, text="シリアル番号:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.serial_var = tk.StringVar(value="MOCK001")
        ttk.Entry(settings_frame, textvariable=self.serial_var, width=25).grid(row=2, column=1, pady=2)
        
        # ユーザー定義名
        ttk.Label(settings_frame, text="ユーザー名:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.user_name_var = tk.StringVar(value="MockCamera")
        ttk.Entry(settings_frame, textvariable=self.user_name_var, width=25).grid(row=3, column=1, pady=2)
        
        # 画像設定
        image_frame = ttk.LabelFrame(left_frame, text="画像設定", padding=10)
        image_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 解像度
        ttk.Label(image_frame, text="幅:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.width_var = tk.IntVar(value=640)
        ttk.Spinbox(image_frame, textvariable=self.width_var, from_=64, to=4096, width=10).grid(row=0, column=1, pady=2)
        
        ttk.Label(image_frame, text="高さ:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.height_var = tk.IntVar(value=480)
        ttk.Spinbox(image_frame, textvariable=self.height_var, from_=64, to=4096, width=10).grid(row=1, column=1, pady=2)
        
        # フレームレート
        ttk.Label(image_frame, text="FPS:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.fps_var = tk.DoubleVar(value=30.0)
        ttk.Spinbox(image_frame, textvariable=self.fps_var, from_=1, to=120, width=10).grid(row=2, column=1, pady=2)
        
        # カラーモード
        self.color_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(image_frame, text="カラーモード", variable=self.color_var).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        # 画像ソース
        source_frame = ttk.LabelFrame(left_frame, text="画像ソース", padding=10)
        source_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.source_var = tk.StringVar(value="")
        ttk.Entry(source_frame, textvariable=self.source_var, width=30).pack(fill=tk.X, pady=2)
        
        btn_frame = ttk.Frame(source_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="フォルダ選択", command=self._select_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="ファイル選択", command=self._select_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="クリア", command=lambda: self.source_var.set("")).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(source_frame, text="※空の場合はテストパターンを生成", foreground="gray").pack(anchor=tk.W)
        
        # 制御ボタン
        control_frame = ttk.Frame(left_frame)
        control_frame.pack(fill=tk.X, pady=10)
        
        self.start_btn = ttk.Button(control_frame, text="サーバー起動", command=self._start_server)
        self.start_btn.pack(fill=tk.X, pady=2)
        
        self.stop_btn = ttk.Button(control_frame, text="サーバー停止", command=self._stop_server, state=tk.DISABLED)
        self.stop_btn.pack(fill=tk.X, pady=2)
        
        # ステータス
        status_frame = ttk.LabelFrame(left_frame, text="ステータス", padding=10)
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.status_label = ttk.Label(status_frame, text="停止中", foreground="gray")
        self.status_label.pack(anchor=tk.W)
        
        self.ip_label = ttk.Label(status_frame, text="IP: -")
        self.ip_label.pack(anchor=tk.W)
        
        self.stream_label = ttk.Label(status_frame, text="ストリーム: -")
        self.stream_label.pack(anchor=tk.W)
        
        # 右側: プレビュー＆ログ
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # プレビュー
        preview_frame = ttk.LabelFrame(right_frame, text="プレビュー", padding=5)
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.preview_canvas = tk.Canvas(preview_frame, bg="black", width=480, height=360)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)
        
        preview_controls = ttk.Frame(preview_frame)
        preview_controls.pack(fill=tk.X)
        
        self.preview_btn = ttk.Button(preview_controls, text="プレビュー開始", command=self._toggle_preview)
        self.preview_btn.pack(side=tk.LEFT, padx=2)
        
        ttk.Button(preview_controls, text="画像追加", command=self._add_custom_image).pack(side=tk.LEFT, padx=2)
        
        # ログ
        log_frame = ttk.LabelFrame(right_frame, text="ログ", padding=5)
        log_frame.pack(fill=tk.X)
        
        self.log_text = tk.Text(log_frame, height=8, state=tk.DISABLED)
        self.log_text.pack(fill=tk.X)
        
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
    
    def _log(self, message: str):
        """ログを追加"""
        timestamp = time.strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
    
    def _select_folder(self):
        """フォルダ選択"""
        folder = filedialog.askdirectory()
        if folder:
            self.source_var.set(folder)
    
    def _select_file(self):
        """ファイル選択"""
        file = filedialog.askopenfilename(
            filetypes=[
                ("画像ファイル", "*.png *.jpg *.jpeg *.bmp *.tiff"),
                ("動画ファイル", "*.mp4 *.avi *.mov"),
                ("すべてのファイル", "*.*")
            ]
        )
        if file:
            self.source_var.set(file)
    
    def _start_server(self):
        """サーバー起動"""
        try:
            config = MockCameraConfig(
                vendor=self.vendor_var.get(),
                model=self.model_var.get(),
                serial_number=self.serial_var.get(),
                user_defined_name=self.user_name_var.get(),
                width=self.width_var.get(),
                height=self.height_var.get(),
                frame_rate=self.fps_var.get(),
                pixel_format=PixelFormat.BGR8 if self.color_var.get() else PixelFormat.MONO8
            )
            
            source = self.source_var.get() if self.source_var.get() else None
            
            self.server = GigEMockCameraServer(config=config, image_source=source)
            self.server.on_log = self._log
            
            if self.server.start():
                self._log("サーバーを起動しました")
                self.start_btn.configure(state=tk.DISABLED)
                self.stop_btn.configure(state=tk.NORMAL)
                self._update_status()
            else:
                messagebox.showerror("エラー", "サーバーの起動に失敗しました")
                
        except Exception as e:
            messagebox.showerror("エラー", f"起動エラー: {e}")
    
    def _stop_server(self):
        """サーバー停止"""
        if self.server:
            self.server.stop()
            self.server = None
            self._log("サーバーを停止しました")
        
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self._update_status()
    
    def _update_status(self):
        """ステータス更新"""
        if self.server and self.server.is_running:
            self.status_label.configure(text="実行中", foreground="green")
            self.ip_label.configure(text=f"IP: {self.server.local_ip}:3956")
            if self.server.is_streaming:
                self.stream_label.configure(text="ストリーム: 配信中", foreground="blue")
            else:
                self.stream_label.configure(text="ストリーム: 待機中", foreground="gray")
        else:
            self.status_label.configure(text="停止中", foreground="gray")
            self.ip_label.configure(text="IP: -")
            self.stream_label.configure(text="ストリーム: -")
        
        # 定期更新
        self.root.after(1000, self._update_status)
    
    def _toggle_preview(self):
        """プレビュー切り替え"""
        if self._preview_running:
            self._stop_preview()
        else:
            self._start_preview()
    
    def _start_preview(self):
        """プレビュー開始"""
        if not self.server or not self.server._images:
            self._log("プレビューする画像がありません")
            return
        
        self._preview_running = True
        self.preview_btn.configure(text="プレビュー停止")
        self._preview_thread = threading.Thread(target=self._preview_loop, daemon=True)
        self._preview_thread.start()
    
    def _stop_preview(self):
        """プレビュー停止"""
        self._preview_running = False
        self.preview_btn.configure(text="プレビュー開始")
    
    def _preview_loop(self):
        """プレビューループ"""
        while self._preview_running and self.server:
            try:
                if self.server._images:
                    idx = self.server._current_image_index
                    if idx < len(self.server._images):
                        image = self.server._images[idx]
                        self._show_image(image)
                time.sleep(1.0 / self.server.config.frame_rate)
            except Exception as e:
                print(f"プレビューエラー: {e}")
                break
    
    def _show_image(self, image: np.ndarray):
        """画像を表示"""
        try:
            # サイズ取得
            canvas_w = self.preview_canvas.winfo_width()
            canvas_h = self.preview_canvas.winfo_height()
            
            if canvas_w < 10 or canvas_h < 10:
                return
            
            # リサイズ
            h, w = image.shape[:2]
            scale = min(canvas_w / w, canvas_h / h)
            new_w, new_h = int(w * scale), int(h * scale)
            
            resized = cv2.resize(image, (new_w, new_h))
            
            # BGRからRGBに変換
            if len(resized.shape) == 3:
                rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            else:
                rgb = cv2.cvtColor(resized, cv2.COLOR_GRAY2RGB)
            
            # Tkinter用に変換
            pil_image = Image.fromarray(rgb)
            tk_image = ImageTk.PhotoImage(pil_image)
            
            # 表示
            self._current_image = tk_image  # 参照を保持
            self.preview_canvas.delete("all")
            x = (canvas_w - new_w) // 2
            y = (canvas_h - new_h) // 2
            self.preview_canvas.create_image(x, y, anchor=tk.NW, image=tk_image)
            
        except Exception as e:
            print(f"画像表示エラー: {e}")
    
    def _add_custom_image(self):
        """カスタム画像を追加"""
        if not self.server:
            messagebox.showwarning("警告", "先にサーバーを起動してください")
            return
        
        file = filedialog.askopenfilename(
            filetypes=[
                ("画像ファイル", "*.png *.jpg *.jpeg *.bmp *.tiff"),
                ("すべてのファイル", "*.*")
            ]
        )
        
        if file:
            try:
                image = cv2.imread(file, cv2.IMREAD_UNCHANGED)
                if image is not None:
                    self.server.add_image(image)
                    self._log(f"画像を追加: {os.path.basename(file)}")
                else:
                    messagebox.showerror("エラー", "画像を読み込めませんでした")
            except Exception as e:
                messagebox.showerror("エラー", f"エラー: {e}")
    
    def run(self):
        """GUIを実行"""
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()
    
    def _on_close(self):
        """終了処理"""
        self._stop_preview()
        if self.server:
            self.server.stop()
        self.root.destroy()


def main():
    app = MockCameraServerGUI()
    app.run()


if __name__ == "__main__":
    main()
