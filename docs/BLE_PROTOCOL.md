# BLE GATT Protocol Documentation

This document describes the BLE GATT protocol used by the SAR Scanner to stream sightings to a companion mobile app.

## Overview

The Raspberry Pi SAR Scanner acts as a **BLE Peripheral (GATT Server)** that:
1. Advertises its presence with service UUID and basic status
2. Accepts connections from a companion app (BLE Central)
3. Streams real-time sightings via GATT notifications
4. Supports remote control and bulk data download

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Raspberry Pi                                                │
│                                                             │
│  ┌─────────────┐    SQLite     ┌──────────────────────────┐ │
│  │  Scanner    │──────────────▶│   BLE GATT Publisher     │ │
│  │  (hci1)     │   (polling)   │   (hci0 - built-in BT)   │ │
│  └─────────────┘               └──────────────────────────┘ │
│                                          │                  │
└──────────────────────────────────────────│──────────────────┘
                                           │ BLE GATT
                                           ▼
                               ┌───────────────────────┐
                               │  Companion App        │
                               │  (BLE Central/Client) │
                               └───────────────────────┘
```

## Service & Characteristics

### Service UUID
```
12345678-1234-5678-1234-56789abc0001
```

### Characteristics

| Name | UUID | Properties | Description |
|------|------|------------|-------------|
| **LiveFeed** | `...0002` | Notify | Real-time sighting stream |
| **Control** | `...0003` | Write, Write Without Response | Remote commands |
| **Status** | `...0004` | Read, Notify | Device status (JSON) |
| **BulkTransfer** | `...0005` | Notify, Write | Historical data download |

## Data Formats

### Bluetooth Sighting Packet (LiveFeed)

Sent when a new Bluetooth device is detected.

```
Offset  Size  Field           Description
------  ----  -----           -----------
0       1     Type            0x01 (Bluetooth)
1       2     Sequence        Packet sequence number (little-endian)
3       6     MAC             Device MAC address
9       4     Timestamp       Unix epoch (little-endian, seconds)
13      4     Latitude        lat × 10^7 (signed int, little-endian)
17      4     Longitude       lon × 10^7 (signed int, little-endian)
21      1     RSSI            Signal strength (signed byte, dBm)
22      1     TX Power        TX power level (signed byte) or 0x7F if unknown
23      1     Flags           bit0=has_name, bit1=has_manufacturer
24      1     Name Length     Length of device name (0-32)
25      1     Mfr Length      Length of manufacturer string (0-20)
26      var   Name            UTF-8 device name (if present)
26+N    var   Manufacturer    UTF-8 manufacturer name (if present)
```

**Special values:**
- Latitude/Longitude: `0x7FFFFFFF` = no GPS fix
- RSSI: `-128` = unknown
- TX Power: `127` = unknown

### WiFi Sighting Packet (LiveFeed)

Sent when a WiFi association request is captured.

```
Offset  Size  Field           Description
------  ----  -----           -----------
0       1     Type            0x02 (WiFi)
1       2     Sequence        Packet sequence number (little-endian)
3       6     MAC             Device MAC address
9       4     Timestamp       Unix epoch (little-endian)
13      4     Latitude        lat × 10^7 (signed int)
17      4     Longitude       lon × 10^7 (signed int)
21      1     RSSI            Signal strength (signed byte)
22      1     SSID Length     Length of SSID string (0-32)
23      var   SSID            UTF-8 encoded SSID
```

### Status Characteristic (JSON)

Read at any time or received via notification after certain commands.

```json
{
  "v": 1,              // Protocol version
  "gps_fix": 3,        // 0=none, 2=2D, 3=3D
  "gps_sats": 8,       // Satellites used
  "time_src": "gps",   // "gps", "rtc", or "system"
  "ts": 1739836800,    // Current Unix timestamp
  "queue": 5,          // Pending sightings in queue
  "id": "Scanner 1",   // Scanner identifier
  "ver": "1.0.0",      // Publisher version
  "bt_cnt": 1523,      // Total BT sightings
  "wifi_cnt": 847,     // Total WiFi sightings
  "active": true,      // Publisher running
  "paused": false      // Feed paused
}
```

### Control Commands

Write to Control characteristic to send commands.

| Command | Byte | Payload | Description |
|---------|------|---------|-------------|
| Pause Feed | `0x01` | - | Stop live notifications |
| Resume Feed | `0x02` | - | Resume live notifications |
| Set RSSI Filter | `0x10` | `int8` | Minimum RSSI in dBm |
| Set Aggregation | `0x20` | `uint16` | Min ms between notifications |
| Bulk Request | `0x30` | See below | Request historical data |
| Ping | `0x40` | - | Request status notification |
| Get Stats | `0x41` | - | Request status notification |

### Bulk Transfer Protocol

**Request format (write to BulkTransfer):**
```
Offset  Size  Field           Description
------  ----  -----           -----------
0       4     ts_start        Start timestamp (Unix, little-endian)
4       4     ts_end          End timestamp (Unix, little-endian)
8       1     type            0=both, 1=BT only, 2=WiFi only
```

**Response format (notifications from BulkTransfer):**
```
Offset  Size  Field           Description
------  ----  -----           -----------
0       2     chunk_id        Current chunk index (0-based)
2       2     total_chunks    Total number of chunks
4       var   data            Concatenated sighting packets
```

If `total_chunks` is 0, no sightings were found in the requested range.

## Advertising Data

When not connected, the scanner advertises:

- **Local Name:** "SAR-Scanner" (configurable)
- **Service UUID:** Custom 128-bit UUID
- **Manufacturer Data (8 bytes):**
  - Byte 0: Protocol version
  - Byte 1: GPS fix status (0/2/3)
  - Bytes 2-4: BT sighting count (24-bit, little-endian)
  - Bytes 5-7: WiFi sighting count (24-bit, little-endian)

## Usage Example (Companion App)

### iOS/Android Pseudocode

```swift
// 1. Scan for devices advertising our service UUID
scanner.scan(withServices: [SERVICE_UUID])

// 2. Connect to discovered scanner
peripheral.connect()

// 3. Discover our service and characteristics
peripheral.discoverServices([SERVICE_UUID])
peripheral.discoverCharacteristics([LIVE_FEED_UUID, CONTROL_UUID, STATUS_UUID])

// 4. Read current status
let status = peripheral.readValue(for: statusCharacteristic)

// 5. Subscribe to live feed
peripheral.setNotify(true, for: liveFeedCharacteristic)

// 6. Handle incoming sightings
func peripheral(didUpdateValue data: Data, for: liveFeedCharacteristic) {
    let type = data[0]
    if type == 0x01 {
        let sighting = decodeBTSighting(data)
        displayOnMap(sighting)
    } else if type == 0x02 {
        let sighting = decodeWiFiSighting(data)
        displayOnMap(sighting)
    }
}

// 7. Optional: Request historical data
let request = encodeBulkRequest(startTime, endTime, type: 0)
peripheral.writeValue(request, for: bulkTransferCharacteristic)
```

## Configuration

In `settings.py`:

```python
BLE_PUBLISH_ENABLED = False              # Set to True to enable
BLE_PUBLISH_INTERFACE = "hci0"           # Built-in BT (scanner uses hci1)
BLE_PUBLISH_DEVICE_NAME = "SAR-Scanner"  # BLE advertised name
BLE_PUBLISH_POLL_INTERVAL = 0.5          # DB poll interval (seconds)
BLE_PUBLISH_AGGREGATION_MS = 200         # Min ms between notifications
BLE_PUBLISH_MIN_RSSI = -100              # Default RSSI filter
```

## Requirements

- Raspberry Pi with dual Bluetooth (built-in + USB dongle)
- BlueZ 5.50+
- Python packages:
  ```bash
  sudo apt install python3-dbus python3-gi
  ```

## Standalone Testing

Run the publisher standalone for testing:

```bash
# Default settings
sudo python3 ble_publisher.py

# Custom options
sudo python3 ble_publisher.py --interface hci0 --name "Test-Scanner" --db /path/to/results.db
```

## Troubleshooting

### "Bluetooth adapter not found"
- Check adapter is present: `hciconfig -a`
- Ensure hci0 is not blocked: `rfkill list`
- Unblock if needed: `sudo rfkill unblock bluetooth`

### "Failed to register GATT application"
- Ensure BlueZ 5.50+: `bluetoothctl --version`
- Check D-Bus permissions: user should be in `bluetooth` group
- Restart Bluetooth: `sudo systemctl restart bluetooth`

### No notifications received
- Verify client has subscribed to LiveFeed characteristic
- Check `feed_paused` is false in Status
- Ensure RSSI filter isn't too aggressive

## Protocol Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-18 | Initial release |
