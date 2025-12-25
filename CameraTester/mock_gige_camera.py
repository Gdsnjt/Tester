"""
Mock GigE Vision Camera Server
Emulates a real GigE Vision camera on the network
"""
import os
import glob
import threading
import time
import socket
from typing import List, Optional
import numpy as np
import cv2

from gige_protocol import GVCPServer, GVSPServer, GVSPPixelType


class MockGigECamera:
    """
    Mock GigE Vision Camera Server
    
    Emulates a GigE Vision camera that can be discovered and controlled
    via standard GenTL Producers (Harvester)
    """
    
    def __init__(self, 
                 device_info: Optional[dict] = None,
                 image_source: Optional[str] = None,
                 bind_ip: str = "0.0.0.0",
                 gvcp_port: int = 3956,
                 gvsp_port: int = 50000):
        
        if device_info is None:
            device_info = {
                'vendor': 'MockCam Corp',
                'model': 'VirtualCam-1',
                'serial': 'MOCK001',
                'user_name': 'TestCamera_1'
            }
        
        # 実際IPをdevice_infoに記録（レジスタ用）
        device_info['local_ip'] = bind_ip if bind_ip != "0.0.0.0" else "192.168.1.100"
        
        self.device_info = device_info
        self.bind_ip = bind_ip
        self.gvcp_port = gvcp_port
        self.gvsp_port = gvsp_port
        
        # GVCPサーバーは0.0.0.0でバインド（ブロードキャスト受信のため）
        self.gvcp_server = GVCPServer(device_info, "0.0.0.0", gvcp_port, gvsp_port)
        self.gvsp_server = GVSPServer("0.0.0.0", gvsp_port)
        
        self.image_source = image_source
        self.images: List[np.ndarray] = []
        self.current_image_index = 0
        
        self.acquiring = False
        self.acquisition_thread: Optional[threading.Thread] = None
        self.frame_rate = 30.0
        self.frame_id = 0
        
        self._load_images()
    
    def _load_images(self):
        """Load images from source"""
        if self.image_source is None:
            default_folder = r"C:\exe\Tester\Tester\CameraTester\mock_images"
            if os.path.exists(default_folder):
                self.image_source = default_folder
            else:
                self._generate_test_images()
                return
        
        if os.path.isdir(self.image_source):
            patterns = ['*.png', '*.jpg', '*.jpeg', '*.bmp']
            files = []
            for pattern in patterns:
                files.extend(glob.glob(os.path.join(self.image_source, pattern)))
            files = sorted(files, key=lambda x: os.path.basename(x).lower())
            
            for f in files:
                img = cv2.imread(f, cv2.IMREAD_COLOR)
                if img is not None:
                    self.images.append(img)
                    print(f"[MockGigE] Loaded: {os.path.basename(f)}")
        
        if not self.images:
            self._generate_test_images()
    
    def _generate_test_images(self):
        """Generate test pattern images"""
        width, height = 640, 480
        
        for i in range(5):
            if i == 0:
                img = np.zeros((height, width, 3), dtype=np.uint8)
                for y in range(height):
                    hue = int((y * 180 / height) % 180)
                    hsv = np.full((1, width, 3), [hue, 255, 255], dtype=np.uint8)
                    img[y:y+1, :] = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
            elif i == 1:
                img = np.zeros((height, width, 3), dtype=np.uint8)
                for x in range(width):
                    ratio = x / width
                    img[:, x] = [int(255 * (1-ratio)), 0, int(255 * ratio)]
            elif i == 2:
                img = np.zeros((height, width, 3), dtype=np.uint8)
                colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
                square_size = 80
                for y in range(0, height, square_size):
                    for x in range(0, width, square_size):
                        color_idx = ((y // square_size) + (x // square_size)) % len(colors)
                        img[y:y+square_size, x:x+square_size] = colors[color_idx]
            elif i == 3:
                img = np.zeros((height, width, 3), dtype=np.uint8)
                img[:] = (20, 40, 60)
                center = (width // 2, height // 2)
                colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
                for idx, r in enumerate(range(20, 200, 40)):
                    cv2.circle(img, center, r, colors[idx % len(colors)], 3)
            else:
                img = np.ones((height, width, 3), dtype=np.uint8) * np.array([40, 60, 80], dtype=np.uint8)
                cv2.putText(img, "Mock GigE Camera", (width//2 - 180, height//2 - 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
                cv2.putText(img, self.device_info['model'], (width//2 - 100, height//2 + 20),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            
            self.images.append(img)
        
        print(f"[MockGigE] Generated {len(self.images)} test images")
    
    def start(self):
        """Start camera server"""
        self.gvcp_server.start()
        self.gvsp_server.start()
        print(f"[MockGigE] '{self.device_info['model']}' started - "
              f"GVCP:{self.gvcp_port}, GVSP:{self.gvsp_port}")
    
    def stop(self):
        """Stop camera server"""
        self.stop_acquisition()
        self.gvcp_server.stop()
        self.gvsp_server.stop()
        print(f"[MockGigE] Camera '{self.device_info['model']}' stopped")
    
    def start_acquisition(self, dest_ip: str, dest_port: int = 50000):
        """Start image acquisition"""
        if self.acquiring:
            return
        
        self.gvsp_server.set_destination(dest_ip, dest_port)
        self.acquiring = True
        self.frame_id = 0
        
        self.acquisition_thread = threading.Thread(target=self._acquisition_loop, daemon=True)
        self.acquisition_thread.start()
        
        print(f"[MockGigE] Acquisition started, streaming to {dest_ip}:{dest_port}")
    
    def stop_acquisition(self):
        """Stop image acquisition"""
        self.acquiring = False
        if self.acquisition_thread:
            self.acquisition_thread.join(timeout=2.0)
            self.acquisition_thread = None
        print("[MockGigE] Acquisition stopped")
    
    def _acquisition_loop(self):
        """Acquisition loop"""
        frame_interval = 1.0 / self.frame_rate
        
        while self.acquiring:
            start_time = time.time()
            
            if self.images:
                img = self.images[self.current_image_index].copy()
                self.current_image_index = (self.current_image_index + 1) % len(self.images)
                
                self.frame_id += 1
                cv2.putText(img, f"Frame: {self.frame_id}", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                img_bgr = cv2.cvtColor(img, cv2.COLOR_BGR2RGB) if len(img.shape) == 3 else img
                
                height, width = img_bgr.shape[:2]
                pixel_format = GVSPPixelType.RGB8 if len(img_bgr.shape) == 3 else GVSPPixelType.MONO8
                
                self.gvsp_server.send_image(img_bgr.tobytes(), width, height, pixel_format)
            
            elapsed = time.time() - start_time
            sleep_time = max(0, frame_interval - elapsed)
            time.sleep(sleep_time)


def create_mock_cameras(count: int = 2, bind_ip: str = "0.0.0.0", 
                        base_gvcp_port: int = 3956, 
                        base_gvsp_port: int = 50000) -> List[MockGigECamera]:
    """Create multiple mock GigE cameras with different ports"""
    cameras = []
    
    for i in range(count):
        device_info = {
            'vendor': 'MockCam Corp',
            'model': f'VirtualCam-{i+1}',
            'serial': f'MOCK{i+1:03d}',
            'user_name': f'TestCamera_{i+1}'
        }
        
        gvcp_port = base_gvcp_port + i
        gvsp_port = base_gvsp_port + i
        
        camera = MockGigECamera(
            device_info=device_info, 
            bind_ip=bind_ip,
            gvcp_port=gvcp_port,
            gvsp_port=gvsp_port
        )
        cameras.append(camera)
    
    return cameras


if __name__ == "__main__":
    print("=== Mock GigE Vision Camera Server ===\n")
    
    local_ip = socket.gethostbyname(socket.gethostname())
    print(f"Host IP: {local_ip}\n")
    
    camera = MockGigECamera(bind_ip=local_ip)
    camera.start()
    
    print("\nCamera is running. Press Ctrl+C to stop...")
    print("You can now discover this camera using:")
    print("- Harvester (Python)")
    print("- pylon Viewer (limited support)")
    print("- Any GigE Vision compliant software\n")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping camera...")
        camera.stop()
        print("Done.")
