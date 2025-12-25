"""
GigE Vision Discovery Test
直接ディスカバリーパケットを送信してモックカメラの応答をテスト
"""
import socket
import struct

def send_discovery():
    """ディスカバリーパケットを送信"""
    # ディスカバリーパケット: Magic(0x42) + Flags(0x01) + CMD(0x0002) + Len(0) + ReqID(0xFFFF)
    discovery_packet = struct.pack('>BBHHH', 0x42, 0x01, 0x0002, 0x0000, 0xFFFF)
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(2.0)
    
    print("ディスカバリーパケット送信中...")
    print(f"パケット: {discovery_packet.hex(' ')}")
    
    # ブロードキャストアドレスに送信
    broadcast_addr = ('255.255.255.255', 3956)
    sock.sendto(discovery_packet, broadcast_addr)
    
    print("\n応答待機中...")
    devices = []
    
    try:
        while True:
            data, addr = sock.recvfrom(2048)
            print(f"\n応答受信: {len(data)}バイト from {addr[0]}:{addr[1]}")
            print(f"ヘッダー: {data[:8].hex(' ')}")
            
            if len(data) >= 8:
                magic, flags, command, length, req_id = struct.unpack('>BBHHH', data[:8])
                print(f"  Magic: 0x{magic:02x}")
                print(f"  Flags: 0x{flags:02x}")
                print(f"  Command: 0x{command:04x} (DISCOVERY_ACK)" if command == 0x0003 else f"  Command: 0x{command:04x}")
                print(f"  Length: {length}")
                print(f"  ReqID: 0x{req_id:04x}")
                
                if command == 0x0003 and len(data) >= 8 + 256:
                    ack_data = data[8:]
                    
                    # IP Address (offset 0x0024)
                    ip = ack_data[0x0024:0x0028]
                    print(f"\n  IP Address: {ip[0]}.{ip[1]}.{ip[2]}.{ip[3]}")
                    
                    # Manufacturer Name (offset 0x0048)
                    vendor = ack_data[0x0048:0x0068].rstrip(b'\x00').decode('ascii', errors='ignore')
                    print(f"  Vendor: {vendor}")
                    
                    # Model Name (offset 0x0068)
                    model = ack_data[0x0068:0x0088].rstrip(b'\x00').decode('ascii', errors='ignore')
                    print(f"  Model: {model}")
                    
                    # Serial Number (offset 0x00D8)
                    serial = ack_data[0x00D8:0x00E8].rstrip(b'\x00').decode('ascii', errors='ignore')
                    print(f"  Serial: {serial}")
                    
                    devices.append({
                        'ip': f"{ip[0]}.{ip[1]}.{ip[2]}.{ip[3]}",
                        'vendor': vendor,
                        'model': model,
                        'serial': serial
                    })
    
    except socket.timeout:
        print("\nタイムアウト")
    
    finally:
        sock.close()
    
    print(f"\n検出されたデバイス: {len(devices)}台")
    for i, dev in enumerate(devices):
        print(f"  {i+1}. {dev['vendor']} {dev['model']} ({dev['serial']}) - {dev['ip']}")

if __name__ == "__main__":
    send_discovery()
