"""
統合カメラクライアント
実カメラとモックGigEカメラの両方に対応
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from PIL import Image, ImageTk
from datetime import datetime
import threading
import queue
import time
import numpy as np
import cv2
import os

from harvester_camera import HarvesterCameraProvider


class UnifiedCameraGUI:
    """
    統合カメラGUI
    Harvester経由で実カメラとモックGigE Visionカメラの両方をサポート
    """
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("GigE Visionカメラクライアント (統合版)")
        self.root.geometry("1200x900")
        
        self.provider: HarvesterCameraProvider = None
        self.connected = False
        self.acquiring = False
        
        self.current_image: np.ndarray = None
        self.frame_count = 0
        
        self.image_queue = queue.Queue(maxsize=5)
        self.acquisition_thread = None
        self.display_running = False
        
        self.log_queue = queue.Queue()
        
        self._create_widgets()
        self._process_log_queue()
        
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
    
    def _create_widgets(self):
        """本 UIウィジェットを作成"""
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X)
        
        ttk.Label(top_frame, text="CTIファイル:", font=('', 10, 'bold')).pack(side=tk.LEFT, padx=5)
        self.cti_var = tk.StringVar(value=r"C:\exe\Tester\Tester\CameraTester\ProducerGEV.cti")
        ttk.Entry(top_frame, textvariable=self.cti_var, width=60).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="参照", command=self._browse_cti).pack(side=tk.LEFT, padx=5)
        
        control_frame = ttk.LabelFrame(self.root, text="カメラ制御", padding="10")
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        btn_row1 = ttk.Frame(control_frame)
        btn_row1.pack(fill=tk.X, pady=5)
        
        self.init_btn = ttk.Button(btn_row1, text="初期化", command=self._initialize, width=15)
        self.init_btn.pack(side=tk.LEFT, padx=5)
        
        self.discover_btn = ttk.Button(btn_row1, text="デバイス検出", 
                                       command=self._discover, width=15, state=tk.DISABLED)
        self.discover_btn.pack(side=tk.LEFT, padx=5)
        
        self.connect_btn = ttk.Button(btn_row1, text="接続", 
                                      command=self._connect, width=15, state=tk.DISABLED)
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        
        self.disconnect_btn = ttk.Button(btn_row1, text="切断", 
                                         command=self._disconnect, width=15, state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.LEFT, padx=5)
        
        btn_row2 = ttk.Frame(control_frame)
        btn_row2.pack(fill=tk.X, pady=5)
        
        self.start_btn = ttk.Button(btn_row2, text="取得開始", 
                                    command=self._start_acquisition, width=15, state=tk.DISABLED)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(btn_row2, text="取得停止", 
                                   command=self._stop_acquisition, width=15, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        self.grab_btn = ttk.Button(btn_row2, text="単一取得", 
                                   command=self._grab_single, width=15, state=tk.DISABLED)
        self.grab_btn.pack(side=tk.LEFT, padx=5)
        
        self.save_btn = ttk.Button(btn_row2, text="画像保存", 
                                   command=self._save_image, width=15, state=tk.DISABLED)
        self.save_btn.pack(side=tk.LEFT, padx=5)
        
        device_frame = ttk.LabelFrame(self.root, text="デバイス一覧", padding="10")
        device_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        list_frame = ttk.Frame(device_frame)
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        columns = ("番号", "メーカー", "型番", "シリアル", "名称")
        self.device_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=6)
        
        for col in columns:
            self.device_tree.heading(col, text=col)
            self.device_tree.column(col, width=100 if col != "名称" else 150)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.device_tree.yview)
        self.device_tree.configure(yscrollcommand=scrollbar.set)
        
        self.device_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.device_tree.bind('<<TreeviewSelect>>', self._on_device_select)
        
        display_frame = ttk.LabelFrame(self.root, text="画像表示", padding="10")
        display_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.canvas = tk.Canvas(display_frame, width=800, height=600, bg='black')
        self.canvas.pack()
        
        info_frame = ttk.Frame(display_frame)
        info_frame.pack(fill=tk.X, pady=5)
        
        self.info_label = ttk.Label(info_frame, text="画像なし", foreground="gray")
        self.info_label.pack()
        
        log_frame = ttk.LabelFrame(self.root, text="ログ", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, font=('Consolas', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        log_btn_frame = ttk.Frame(log_frame)
        log_btn_frame.pack(fill=tk.X, pady=2)
        ttk.Button(log_btn_frame, text="ログクリア", command=self._clear_log).pack(side=tk.RIGHT)
    
    def _browse_cti(self):
        """CTIファイルを参照"""
        filename = filedialog.askopenfilename(
            title="CTIファイルを選択",
            filetypes=[("本 CTIファイル", "*.cti"), ("全てのファイル", "*.*")]
        )
        if filename:
            self.cti_var.set(filename)
    
    def _initialize(self):
        """Harvesterを初期化"""
        try:
            cti_file = self.cti_var.get()
            if not os.path.exists(cti_file):
                messagebox.showerror("エラー", f"CTIファイルが見つかりません:\n{cti_file}")
                return
            
            self._log(f"CTIファイルで初期化中: {cti_file}")
            
            self.provider = HarvesterCameraProvider()
            if self.provider.initialize(cti_file=cti_file):
                self._log("初期化成功")
                self.discover_btn['state'] = tk.NORMAL
                self.init_btn['state'] = tk.DISABLED
            else:
                self._log("初期化失敗")
                messagebox.showerror("エラー", "Harvesterの初期化に失敗しました")
        
        except Exception as e:
            self._log(f"初期化エラー: {e}")
            messagebox.showerror("エラー", str(e))
    
    def _discover(self):
        """デバイスを検出"""
        if not self.provider:
            return
        
        try:
            self._log("デバイス検出中...")
            
            for item in self.device_tree.get_children():
                self.device_tree.delete(item)
            
            devices = self.provider.discover_devices()
            
            for dev in devices:
                self.device_tree.insert('', tk.END, values=(
                    dev.index,
                    dev.vendor,
                    dev.model,
                    dev.serial_number,
                    dev.user_defined_name
                ))
            
            self._log(f"{len(devices)}台のデバイスを検出")
            
            if devices:
                self.connect_btn['state'] = tk.NORMAL
        
        except Exception as e:
            self._log(f"検出エラー: {e}")
            messagebox.showerror("エラー", str(e))
    
    def _on_device_select(self, event):
        """デバイス選択変更"""
        pass
    
    def _connect(self):
        """選択されたデバイスに接続"""
        selection = self.device_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "デバイスを選択してください")
            return
        
        try:
            item = self.device_tree.item(selection[0])
            device_index = int(item['values'][0])
            
            self._log(f"デバイス {device_index} に接続中...")
            
            if self.provider.connect(device_index):
                self.connected = True
                self._log("接続成功")
                
                self.connect_btn['state'] = tk.DISABLED
                self.disconnect_btn['state'] = tk.NORMAL
                self.start_btn['state'] = tk.NORMAL
                self.grab_btn['state'] = tk.NORMAL
            else:
                self._log("接続失敗")
                messagebox.showerror("エラー", "デバイスへの接続に失敗しました")
        
        except Exception as e:
            self._log(f"接続エラー: {e}")
            messagebox.showerror("エラー", str(e))
    
    def _disconnect(self):
        """デバイスから切断"""
        if self.acquiring:
            self._stop_acquisition()
        
        try:
            if self.provider:
                self.provider.disconnect()
            
            self.connected = False
            self._log("切断しました")
            
            self.disconnect_btn['state'] = tk.DISABLED
            self.connect_btn['state'] = tk.NORMAL
            self.start_btn['state'] = tk.DISABLED
            self.stop_btn['state'] = tk.DISABLED
            self.grab_btn['state'] = tk.DISABLED
            self.save_btn['state'] = tk.DISABLED
        
        except Exception as e:
            self._log(f"切断エラー: {e}")
    
    def _start_acquisition(self):
        """連続取得を開始"""
        if not self.connected:
            return
        
        try:
            if self.provider.start_acquisition():
                self.acquiring = True
                self.display_running = True
                self.frame_count = 0
                
                self.acquisition_thread = threading.Thread(target=self._acquisition_loop, daemon=True)
                self.acquisition_thread.start()
                
                self._start_display_update()
                
                self._log("取得開始")
                
                self.start_btn['state'] = tk.DISABLED
                self.stop_btn['state'] = tk.NORMAL
                self.save_btn['state'] = tk.NORMAL
        
        except Exception as e:
            self._log(f"取得開始エラー: {e}")
            messagebox.showerror("エラー", str(e))
    
    def _stop_acquisition(self):
        """取得停止"""
        self.acquiring = False
        self.display_running = False
        
        try:
            if self.provider:
                self.provider.stop_acquisition()
            
            if self.acquisition_thread:
                self.acquisition_thread.join(timeout=2.0)
                self.acquisition_thread = None
            
            self._log("取得停止")
            
            self.stop_btn['state'] = tk.DISABLED
            self.start_btn['state'] = tk.NORMAL
        
        except Exception as e:
            self._log(f"停止エラー: {e}")
    
    def _grab_single(self):
        """単一画像取得"""
        if not self.connected:
            return
        
        try:
            was_acquiring = self.acquiring
            
            if not was_acquiring:
                self.provider.start_acquisition()
            
            image = self.provider.get_image(timeout=5.0)
            
            if not was_acquiring:
                self.provider.stop_acquisition()
            
            if image:
                self.current_image = image.data
                self.frame_count += 1
                self._display_image(image.data)
                self._log(f"画像取得: {image.width}x{image.height}, フレーム {image.frame_id}")
                self.save_btn['state'] = tk.NORMAL
            else:
                self._log("画像取得失敗 (タイムアウト)")
        
        except Exception as e:
            self._log(f"取得エラー: {e}")
            messagebox.showerror("エラー", str(e))
    
    def _acquisition_loop(self):
        """取得ループスレッド"""
        while self.acquiring:
            try:
                image = self.provider.get_image(timeout=1.0)
                if image:
                    if not self.image_queue.full():
                        self.image_queue.put(image)
                    self.frame_count += 1
            except Exception as e:
                self._log(f"取得エラー: {e}")
                break
    
    def _start_display_update(self):
        """表示更新ループを開始"""
        self._update_display()
    
    def _update_display(self):
        """新しい画像で表示を更新"""
        if self.display_running:
            try:
                while not self.image_queue.empty():
                    image = self.image_queue.get_nowait()
                    self.current_image = image.data
                    self._display_image(image.data)
                    
                    info = f"フレーム: {self.frame_count} | サイズ: {image.width}x{image.height} | " \
                           f"形式: {image.pixel_format} | 時刻: {image.timestamp:.3f}"
                    self.info_label.config(text=info)
            except queue.Empty:
                pass
            except Exception as e:
                self._log(f"表示エラー: {e}")
            
            self.root.after(30, self._update_display)
    
    def _display_image(self, image: np.ndarray):
        """キャンバスに画像を表示"""
        if image is None:
            return
        
        try:
            if len(image.shape) == 2:
                img_rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
            elif image.shape[2] == 3:
                img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                img_rgb = image
            
            height, width = img_rgb.shape[:2]
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            if canvas_width > 1 and canvas_height > 1:
                scale = min(canvas_width / width, canvas_height / height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                
                img_resized = cv2.resize(img_rgb, (new_width, new_height))
            else:
                img_resized = img_rgb
            
            img_pil = Image.fromarray(img_resized)
            img_tk = ImageTk.PhotoImage(image=img_pil)
            
            self.canvas.delete("all")
            self.canvas.create_image(
                canvas_width // 2 if canvas_width > 1 else 400,
                canvas_height // 2 if canvas_height > 1 else 300,
                image=img_tk
            )
            self.canvas.image = img_tk
        
        except Exception as e:
            self._log(f"表示エラー: {e}")
    
    def _save_image(self):
        """現在の画像を保存"""
        if self.current_image is None:
            messagebox.showwarning("警告", "保存する画像がありません")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("本 PNGファイル", "*.png"), ("本 JPEGファイル", "*.jpg"), ("全てのファイル", "*.*")]
        )
        
        if filename:
            try:
                cv2.imwrite(filename, self.current_image)
                self._log(f"画像保存: {filename}")
                messagebox.showinfo("成功", f"画像を保存しました:\n{filename}")
            except Exception as e:
                self._log(f"保存エラー: {e}")
                messagebox.showerror("エラー", str(e))
    
    def _log(self, message: str):
        """ログメッセージを追加"""
        self.log_queue.put(message)
    
    def _process_log_queue(self):
        """ログキューを処理"""
        while not self.log_queue.empty():
            try:
                message = self.log_queue.get_nowait()
                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
                self.log_text.see(tk.END)
            except queue.Empty:
                break
        
        self.root.after(100, self._process_log_queue)
    
    def _clear_log(self):
        """ログをクリア"""
        self.log_text.delete(1.0, tk.END)
    
    def _on_closing(self):
        """ウィンドウを閉じる処理"""
        if self.acquiring:
            self._stop_acquisition()
        
        if self.connected:
            self._disconnect()
        
        if self.provider:
            self.provider.cleanup()
        
        self.root.destroy()


def main():
    """メイン関数"""
    root = tk.Tk()
    
    try:
        root.iconbitmap('camera.ico')
    except:
        pass
    
    app = UnifiedCameraGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
