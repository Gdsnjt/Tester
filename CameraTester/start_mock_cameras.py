"""
Mock GigE Camera Server Launcher
Start one or more mock GigE Vision cameras
"""
import sys
import socket
import time
from mock_gige_camera import MockGigECamera, create_mock_cameras


def get_local_ip():
    """Get local IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except:
        return "127.0.0.1"


def main():
    print("="*60)
    print("Mock GigE Vision Camera Server")
    print("="*60)
    print()
    
    local_ip = get_local_ip()
    print(f"Host IP Address: {local_ip}")
    print()
    
    # デフォルトを1台に変更（デバッグ用）
    num_cameras = 1
    if len(sys.argv) > 1:
        try:
            num_cameras = int(sys.argv[1])
        except:
            pass
    
    print(f"Starting {num_cameras} mock camera(s)...")
    print()
    
    cameras = create_mock_cameras(num_cameras, bind_ip=local_ip)
    
    for camera in cameras:
        camera.start()
        print(f"  ✓ {camera.device_info['model']} ({camera.device_info['serial']}) - "
              f"GVCP:{camera.gvcp_port}, GVSP:{camera.gvsp_port}")
    
    print()
    print("All cameras are now running!")
    print()
    print("These cameras can be discovered by:")
    print("  - Harvester (Python GigE Vision client)")
    print("  - pylon Viewer (Basler, limited compatibility)")
    print("  - Any GenTL-compatible software")
    print()
    print(f"GVCP Port: 3956 (UDP, 全カメラ共通)")
    print(f"GVSP Ports: 50000-{49999+num_cameras} (UDP)")
    print()
    print("To connect from Python:")
    print("  from harvester_camera import HarvesterCameraProvider")
    print("  provider = HarvesterCameraProvider()")
    print('  provider.initialize(cti_file="ProducerGEV.cti")')
    print("  devices = provider.discover_devices()")
    print("  provider.connect(0)")
    print()
    print("Press Ctrl+C to stop all cameras...")
    print()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nStopping cameras...")
        for camera in cameras:
            camera.stop()
        print("All cameras stopped.")
        print("Goodbye!")


if __name__ == "__main__":
    main()
