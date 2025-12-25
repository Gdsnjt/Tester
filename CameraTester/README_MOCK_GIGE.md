# Mock GigE Vision Camera System

## Overview
Complete GigE Vision camera emulation system. Mock cameras can be discovered and controlled through Harvester, just like real GigE cameras.

## Architecture

```
┌─────────────────────────┐
│   Client Application    │
│   (unified_client.py)   │
└───────────┬─────────────┘
            │
            │ Harvester API
            │
┌───────────▼─────────────┐
│   GenTL Producer (CTI)  │
│   (ProducerGEV.cti)     │
└───────────┬─────────────┘
            │
            │ GigE Vision Protocol
            │
    ┌───────┴────────┐
    │                │
┌───▼───────┐  ┌────▼────────┐
│ Real      │  │ Mock GigE   │
│ Camera    │  │ Server      │
│ (Hardware)│  │ (Software)  │
└───────────┘  └─────────────┘
```

## Files

### Core Implementation
- **gige_protocol.py** - GigE Vision protocol (GVCP/GVSP)
- **mock_gige_camera.py** - Mock camera server implementation
- **mock_camera.py** - Legacy compatibility wrapper

### Client Applications
- **unified_client.py** - Unified GUI for both real and mock cameras
- **harvester_camera.py** - Real camera provider (unchanged)
- **start_mock_cameras.py** - Launch mock camera servers

## Usage

### 1. Start Mock Camera Server(s)

```bash
# Start 2 mock cameras (default)
python start_mock_cameras.py

# Start 5 mock cameras
python start_mock_cameras.py 5
```

### 2. Connect from Client

```bash
python unified_client.py
```

**Steps:**
1. Click "Initialize" (loads CTI file)
2. Click "Discover Devices" (finds real + mock cameras)
3. Select a camera from the list
4. Click "Connect"
5. Click "Start Acquisition" or "Grab Single"

### 3. Programmatic Usage

```python
from harvester_camera import HarvesterCameraProvider

# Initialize (same for real and mock)
provider = HarvesterCameraProvider()
provider.initialize(cti_file="ProducerGEV.cti")

# Discover devices (real and mock together)
devices = provider.discover_devices()
for i, dev in enumerate(devices):
    print(f"{i}: {dev.vendor} {dev.model} ({dev.serial_number})")

# Connect to any device (real or mock)
provider.connect(0)

# Start acquisition
provider.start_acquisition()

# Get images
image = provider.get_image(timeout=5.0)
if image:
    print(f"Got image: {image.width}x{image.height}")

# Cleanup
provider.cleanup()
```

## Protocol Implementation

### GVCP (Control Protocol)
- Port: **3956/UDP**
- Commands:
  - `DISCOVERY_CMD` - Device discovery
  - `READREG_CMD` - Read bootstrap registers
  - `WRITEREG_CMD` - Write registers
  - `READMEM_CMD` - Read memory

### GVSP (Streaming Protocol)
- Port: **50000/UDP**
- Packets:
  - Leader - Frame metadata
  - Payload - Image data chunks
  - Trailer - End of frame

### Bootstrap Registers
Implemented registers (0x0000-0x0A00):
- Device information (vendor, model, serial)
- Network configuration (IP, subnet, gateway)
- Channel ports (GVCP, GVSP)
- Capabilities and status

## Mock Camera Features

- **Network Discovery** - Responds to GigE Vision discovery broadcasts
- **Multiple Cameras** - Run multiple independent cameras
- **Image Sources**:
  - Default: Generated test patterns
  - Custom: Load from `mock_images/` folder
  - Supports: PNG, JPG, BMP formats
- **Continuous Streaming** - 30 FPS (configurable)
- **Standard Compliance** - Compatible with GenTL Producers

## Network Configuration

Mock cameras bind to your local IP address automatically.

**Example:**
- Host IP: `192.168.1.100`
- Camera 1: `192.168.1.100:3956` (GVCP), `192.168.1.100:50000` (GVSP)
- Camera 2: `192.168.1.101:3956` (GVCP), `192.168.1.101:50000` (GVSP)

**Firewall:** Allow UDP ports 3956 and 50000

## Limitations

### Full Support
✅ Harvester discovery and connection
✅ Continuous image acquisition
✅ Single frame grab
✅ Multiple cameras
✅ Standard pixel formats (Mono8, RGB8)

### Limited/No Support
❌ pylon Viewer (Basler-specific extensions required)
❌ Advanced GenICam features (limited XML)
❌ Hardware triggers
❌ Precise timestamps
❌ Action commands

## Troubleshooting

**Q: Cameras not discovered?**
- Check firewall (allow UDP 3956, 50000)
- Verify CTI file path
- Check `start_mock_cameras.py` is running

**Q: Connection timeout?**
- Ensure mock server is running
- Verify network connectivity
- Check no port conflicts

**Q: No images received?**
- Check GVSP port 50000 is open
- Verify acquisition started
- Check mock camera logs

## Development

Add custom test images:
```bash
mkdir mock_images
# Add your PNG/JPG files here
# They will be loaded automatically
```

Modify camera parameters:
```python
camera = MockGigECamera(
    device_info={
        'vendor': 'MyCompany',
        'model': 'TestCam-X',
        'serial': 'ABC123',
        'user_name': 'Lab Camera'
    },
    image_source='my_images/',
    bind_ip='192.168.1.150'
)
```

## Compatibility

- **Python**: 3.7+
- **Libraries**: numpy, opencv-python, Pillow
- **GenTL**: Any GigE Vision Producer
- **Tested With**:
  - Harvester (Python)
  - Basic GigE Vision clients

---

**Note:** This is a development/testing tool. Mock cameras emulate the GigE Vision protocol but are not suitable for production use or as replacements for actual camera hardware.
