# WiFi Scanner Setup & Usage

## Overview

The WiFi scanner captures 802.11 association requests (probe requests) from WiFi devices in the area. It identifies devices attempting to connect to known networks, which can help locate devices that previously connected to the missing person's home WiFi.

## Setup

### 1. WiFi Adapter Requirements

- USB WiFi adapter capable of monitor mode (e.g., Alfa AWUS036NHA, Ralink RT3070)
- Must support Linux and monitor mode

### 2. Install Dependencies

```bash
# Ubuntu/Debian
sudo apt-get install scapy python3-scapy aircrack-ng wireless-tools

# Or via pip
pip install scapy
```

### 3. Enable Monitor Mode

```bash
# Identify your USB WiFi adapter
ifconfig -a
# or
iw dev

# Take down the interface
sudo ifconfig wlan0 down

# Enable monitor mode (method 1: using airmon-ng)
sudo airmon-ng check kill
sudo airmon-ng start wlan0

# Or manually (method 2)
sudo iw dev wlan0 set type monitor
sudo ifconfig wlan0 up

# Verify monitor mode
iwconfig wlan0
# Should show "Mode:Monitor"
```

### 4. Configuration

Edit `settings.py`:

```python
SCAN_MODE = "both"           # Options: "bt", "wifi", or "both"
WIFI_INTERFACE = "wlan0"     # Your interface in monitor mode
KNOWN_WIFIS = [
    "Home_Network",
    "Office_WiFi",
    "Cafe_Network"
]
# Leave empty to capture ALL SSIDs (not recommended - high packet volume)
```

## Running the Scanner

### BT Only
```bash
python3 main.py  # With SCAN_MODE = "bt"
```

### WiFi Only
```bash
sudo python3 main.py  # With SCAN_MODE = "wifi" (requires root for packet capture)
```

### Both BT and WiFi
```bash
sudo python3 main.py  # With SCAN_MODE = "both"
```

## Console Output Example

```
============================================================
SAR BT+WiFi Scanner
============================================================
Scan Mode: both
Scanner ID: Scanner 1
USB storage: /mnt/pendrive
SD storage: /home/grpck/
BT device: hci1
WiFi interface: wlan0
============================================================

Initializing GPS...
✓ GPS: 12 satellites, HDOP=1.2
Initializing database...
Starting BT and WiFi scanners...
WiFi scanner started on wlan0

[BT] 00:1A:2B:3C:4D:5E - Device Name (RSSI: -65)
[WiFi] AA:BB:CC:DD:EE:FF -> Home_Network (RSSI: -45)
[BT] 11:22:33:44:55:66 - Another Device (RSSI: -72)
[WiFi] 99:88:77:66:55:44 -> Office_WiFi (RSSI: -52)
```

## Database Output

### WiFi Devices Table
```
SELECT * FROM wifi_devices;
```

| mac | first_seen | last_seen | vendor |
|-----|-----------|-----------|--------|
| AA:BB:CC:DD:EE:FF | 1707818400 | 1707818500 | - |

### WiFi Associations Table
```
SELECT mac, ssid, rssi, lat, lon FROM wifi_associations 
ORDER BY ts_unix DESC LIMIT 20;
```

| mac | ssid | rssi | lat | lon |
|-----|------|------|-----|-----|
| AA:BB:CC:DD:EE:FF | Home_Network | -45 | 52.123 | 21.456 |
| 99:88:77:66:55:44 | Office_WiFi | -52 | 52.124 | 21.457 |

## Querying Results

```bash
# All SSIDs seen
sqlite3 results.db "SELECT DISTINCT ssid FROM wifi_associations;"

# Devices that connected to a specific SSID
sqlite3 results.db "SELECT DISTINCT mac FROM wifi_associations WHERE ssid='Home_Network';"

# Timeline of a specific device
sqlite3 results.db "SELECT ts_unix, ssid, rssi, lat, lon FROM wifi_associations WHERE mac='AA:BB:CC:DD:EE:FF' ORDER BY ts_unix;"

# Recent activity (last hour)
sqlite3 results.db "SELECT mac, ssid, rssi, datetime(ts_unix, 'unixepoch') FROM wifi_associations WHERE ts_unix > (SELECT MAX(ts_unix) - 3600 FROM wifi_associations) ORDER BY ts_unix DESC;"
```

## Troubleshooting

### "Permission denied" error
- WiFi packet capture requires root. Run with `sudo python3 main.py`

### "Interface not found" or "not in monitor mode"
- Verify interface name: `ifconfig -a` or `iw dev`
- Check monitor mode: `iwconfig wlan0` should show `Mode:Monitor`
- Re-enable monitor mode: `sudo airmon-ng start wlan0`

### No packets captured
- Ensure interface is correct
- Check that SSID filtering isn't too restrictive
- Verify WiFi devices are actually broadcasting probe requests
- Monitor mode must be active and working

### High packet volume / slow database
- Set `KNOWN_WIFIS` to specific networks instead of capturing all
- Or add rate limiting to the wifi_scanner.py

## Notes

- The scanner captures association requests (probe requests) - not a passive network monitor
- Only visible if devices are actively seeking networks
- SSIDs might be hidden (shown as `<hidden>`)
- Data is stamped with GPS coordinates if available
- Signal strength (RSSI) helps estimate distance
