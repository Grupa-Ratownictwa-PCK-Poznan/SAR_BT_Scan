# SAR BT+WiFi Scan — Bluetooth & WiFi Scanner for Search and Rescue (SAR)

**SAR_BT_Scan** is an open-source tool by **Grupa Ratownictwa PCK Poznań** designed to assist Search and Rescue (SAR) operations.  
It continuously scans **Bluetooth Low Energy (BLE) beacons** and **WiFi probe requests**, tags them with GPS coordinates and timestamps, and stores the data in a local SQLite database for post-mission analysis and visualization.

---

## 🌍 Purpose

In SAR operations, missing persons often carry devices that emit wireless signals — phones, smartwatches, fitness bands, etc.  
This project provides a **portable multi-protocol scanner** that moves with rescuers and records:
- **Bluetooth signals** from all nearby devices
- **WiFi association requests** that identify networks the device tried to connect to (e.g., home WiFi)

After the mission, the data can be reviewed to find potential devices belonging to the missing person and correlate them with known networks.

---

## 🧩 Hardware Setup

The prototype has been successfully tested on:

| Component | Model / Notes |
|------------|---------------|
| **Host** | Raspberry Pi 5 (4 GB) with Raspberry Pi OS |
| **Bluetooth Adapter** | TP-Link UB500 Plus (Bluetooth 5.0, external antenna) |
| **WiFi Adapter** | USB adapter capable of monitor mode (e.g., Alfa AWUS036NHA, Ralink RT3070) |
| **GPS Receiver** | VK-162 USB GPS dongle |
| **Storage** | USB pendrive for safe data offload |
| **Power** | Powerbank (approx. 5 W draw — ~8 h runtime on 10 000 mAh) |

![Prototype](https://drive.google.com/uc?export=view&id=1jDb16UQ4cg9WnSK-n0fTD6O_-fwnG6FV)
![Prototype](https://drive.google.com/uc?export=view&id=1cIs_jqTanOg82i_qh1hnH-aQ7wgvCcVy)

---

## 🧠 Project Overview

### Main Features
- Real-time **Bluetooth beacon scanning** (BLE advertisements)
- **WiFi association capture** — identify devices connecting to known networks
- **GPS integration** — coordinates and time tagging for all detections
- **SQLite storage** with optimized schema and WAL mode
- **Automatic manufacturer resolution** (Bluetooth SIG company IDs)
- **Dual-mode operation** — scan BT only, WiFi only, or both simultaneously
- **Supervisor watchdog** — keeps scanner running, creates timestamped database backups
- **Configurable paths and adapter names** via `settings.py`

### Repository Layout
```
SAR_BT_Scan/
├── main.py                    # Entry point: mode selector (BT/WiFi/both)
├── scanner.py                 # BLE scanning logic using bleak
├── wifi_scanner.py            # WiFi probe capture using scapy
├── gps_client.py              # GPSD client for GPS coordinates and UTC time
├── storage.py                 # SQLite schema and database helpers
├── supervisor.py              # Watchdog that restarts scanner & backs up DB
├── settings.py                # Configuration (paths, adapters, scan mode)
├── bt_manufacturer_ids.py     # Bluetooth SIG company ID mappings
├── freeze_company_ids.py      # Utility to update company ID database
├── configs/
│   ├── btscanner-supervisor       # Environment file (symlink to /etc/default/)
│   ├── btscanner-supervisor.service  # Systemd unit file
│   └── logtorate.d-btscanner-supervisor # Log rotation config
├── WIFI_SETUP.md              # WiFi adapter setup guide
└── README.md                  # This file
```

---

## ⚙️ Installation

### 1. System Requirements
- Raspberry Pi OS (Bookworm or later)
- Python 3.9+
- GPSD and BlueZ packages
- aircrack-ng and wireless-tools for WiFi

### 2. System Setup
```bash
sudo apt update
sudo apt install -y python3 python3-pip bluez sqlite3 gpsd gpsd-clients python3-gps aircrack-ng wireless-tools
```

### 3. Clone the Repository
```bash
git clone https://github.com/GRPCK-Poznan/SAR_BT_Scan.git
cd SAR_BT_Scan
```

### 4. Install Python Dependencies
```bash
pip install bleak scapy
```

### 5. WiFi Adapter Setup (if using WiFi scanning)
See [WIFI_SETUP.md](WIFI_SETUP.md) for detailed instructions on enabling monitor mode on your USB WiFi adapter.

---

## ⚙️ Configuration

Edit `settings.py` to match your hardware setup:

```python
# Storage paths
USB_STORAGE = "/mnt/pendrive"  # Path for DB backups
SD_STORAGE  = "/home/grpck/"   # Live working directory
DB_FILE     = "results.db"

# Bluetooth configuration
BLEAK_DEVICE = "hci1"          # BLE adapter (often hci1 for TP-Link UB500)
SCANNER_ID   = "Scanner 1"     # Identifier written to each DB record

# Scanning mode and WiFi configuration
SCAN_MODE = "both"             # Options: "bt", "wifi", or "both"
WIFI_INTERFACE = "wlan0"       # USB WiFi adapter interface in monitor mode
KNOWN_WIFIS = []               # List of SSIDs to identify (empty = capture all)
```

### GPS Configuration
Ensure `gpsd` is active and configured to use your receiver (e.g. `/dev/ttyACM0`):

```bash
sudo systemctl enable gpsd
sudo systemctl start gpsd
cgps -s    # Verify GPS fix
```

---

## ▶️ Running the Scanner

### Bluetooth Only
```bash
# With SCAN_MODE = "bt" in settings.py
python3 main.py
```

### WiFi Only
```bash
# With SCAN_MODE = "wifi" in settings.py
# Requires sudo for packet capture
sudo python3 main.py
```

### Both Bluetooth and WiFi
```bash
# With SCAN_MODE = "both" in settings.py
# Requires sudo for WiFi packet capture
sudo python3 main.py
```

### Console Output Example
```
============================================================
SAR BT+WiFi Scanner
============================================================
Scan Mode: both
Scanner ID: Scanner 1
...
Initializing GPS...
✓ GPS: 12 satellites, HDOP=1.2
Initializing database...

[BT] 00:1A:2B:3C:4D:5E - Device Name (RSSI: -65)
[WiFi] AA:BB:CC:DD:EE:FF -> Home_Network (RSSI: -45)
```

---

## 🚀 Service Installation & Management

The scanner can be installed as a **systemd service** for automated start-on-boot and supervisor-based restarts.

### Install as Systemd Service

Copy the service files to system directories:

```bash
# Copy environment file
sudo cp configs/btscanner-supervisor /etc/default/btscanner-supervisor

# Copy systemd unit file
sudo cp configs/btscanner-supervisor.service /etc/systemd/system/

# Copy log rotation config (optional)
sudo cp configs/logtorate.d-btscanner-supervisor /etc/logrotate.d/

# Reload systemd configuration
sudo systemctl daemon-reload
```

### Enable Service at Boot
```bash
sudo systemctl enable btscanner-supervisor
sudo systemctl start btscanner-supervisor
```

### Service Management Commands

**Check Status**
```bash
sudo systemctl status btscanner-supervisor
```
Shows if the service is running, its PID, and recent logs.

**Start the Service**
```bash
sudo systemctl start btscanner-supervisor
```

**Stop the Service**
```bash
sudo systemctl stop btscanner-supervisor
```
This immediately halts the service without uninstalling it.

**Restart the Service**
```bash
sudo systemctl restart btscanner-supervisor
```

**View Real-Time Logs**
```bash
sudo journalctl -u btscanner-supervisor -f
```
Shows live output from the scanner (useful for debugging).

**View Recent Logs**
```bash
sudo journalctl -u btscanner-supervisor -n 50
```
Shows last 50 log entries.

**Disable Auto-Start**
```bash
sudo systemctl disable btscanner-supervisor
```
The service will no longer start automatically on boot.

### Configuration Files

The service behavior is controlled by `/etc/default/btscanner-supervisor`:

```bash
# Main Python command (path to supervisor.py)
BTS_MAIN_CMD="/usr/bin/python3 /home/grpck/sar_bt_scan/sar_bt_scan/main.py"

# Live database (local storage)
BTS_DB_PATH="/home/grpck/results.db"

# Backup destination (USB pendrive)
BTS_DEST_DIR="/mnt/pendrive"

# Log directory
BTS_LOG_DIR="/var/log/btscanner"

# Backup interval (seconds)
BTS_BACKUP_INTERVAL="60"

# Max restart backoff (seconds)
BTS_RESTART_BACKOFF_MAX="60"

# Timezone for timestamps: "local" or "utc"
BTS_TIMEZONE="utc"

# Touch this file to gracefully stop scanner
BTS_STOP_FILE="/run/btscanner-supervisor.stop"
```

To modify settings, edit the file and restart:
```bash
sudo nano /etc/default/btscanner-supervisor
sudo systemctl restart btscanner-supervisor
```

### Supervisor Behavior

The `supervisor.py` process:
- Continuously monitors the main scanner
- Automatically restarts it if it crashes
- Creates timestamped database backups to the USB pendrive
- Clears the live database on each restart to prevent mission data mixing
- Provides resilient operation during long rescue operations

To **gracefully stop** the supervisor without killing the service:
```bash
touch /run/btscanner-supervisor.stop
```

---

## 🗃️ Data Structure

### Bluetooth Tables

**Table: `devices`** (Unique BLE devices)
| Field | Description |
|--------|-------------|
| addr | Bluetooth MAC address |
| first_seen / last_seen | Unix timestamps |
| name | Device name |
| manufacturer_hex / manufacturer | Bluetooth SIG ID + readable name |

**Table: `sightings`** (BLE observations)
| Field | Description |
|--------|-------------|
| id | Auto-increment ID |
| addr | MAC address |
| ts_unix / ts_gps | Time of sighting |
| lat / lon / alt | GPS coordinates |
| rssi | Signal strength (dBm) |
| tx_power | Transmit power (if available) |
| scanner_name | Identifier of scanning device |
| manufacturer | Vendor name |
| service_uuid | BLE service info |
| adv_raw | Optional raw advertisement data |

### WiFi Tables

**Table: `wifi_devices`** (Unique WiFi devices seen)
| Field | Description |
|--------|-------------|
| mac | WiFi MAC address |
| first_seen / last_seen | Unix timestamps |
| vendor | Vendor name (if available) |

**Table: `wifi_associations`** (WiFi networks devices tried to join)
| Field | Description |
|--------|-------------|
| id | Auto-increment ID |
| mac | Device MAC address |
| ts_unix / ts_gps | Time of association attempt |
| lat / lon / alt | GPS coordinates |
| ssid | Network name (plaintext, can be `<hidden>`) |
| rssi | Signal strength (dBm) |
| scanner_name | Identifier of scanning device |

---

## 🧪 Verifying Operation

- **Check Bluetooth adapter**
  ```bash
  hciconfig
  bluetoothctl show
  ```
- **Check WiFi adapter monitor mode** (if enabled)
  ```bash
  iwconfig wlan0  # Should show "Mode:Monitor"
  ```
- **Check GPS**
  ```bash
  cgps -s
  ```
- **Inspect collected data**
  ```bash
  sqlite3 /home/grpck/results.db 'SELECT COUNT(*) FROM sightings;'
  sqlite3 /home/grpck/results.db 'SELECT COUNT(*) FROM wifi_associations;'
  ```

---

## 📤 Data Offload & Analysis

The `supervisor.py` automatically backs up the database to the USB pendrive with timestamps (e.g., `2025-11-04-13-26-08-results.db`). This prevents data mixing when the device boots multiple times during a mission.

At the end of the mission:
- Retrieve `.db` files from `/mnt/pendrive`
- Analyze with examples:

```bash
# All BLE devices (by observation count)
sqlite3 results.db "SELECT addr, name, COUNT(*) FROM sightings GROUP BY addr ORDER BY COUNT(*) DESC LIMIT 20;"

# All WiFi networks seen
sqlite3 results.db "SELECT DISTINCT ssid FROM wifi_associations;"

# Devices connecting to a specific network
sqlite3 results.db "SELECT DISTINCT mac FROM wifi_associations WHERE ssid='Home_Network';"

# Timeline of a single device
sqlite3 results.db "SELECT datetime(ts_unix, 'unixepoch'), ssid, rssi, lat, lon FROM wifi_associations WHERE mac='AA:BB:CC:DD:EE:FF' ORDER BY ts_unix;"

# Last hour of activity
sqlite3 results.db "SELECT mac, ssid, rssi, datetime(ts_unix, 'unixepoch') FROM wifi_associations WHERE ts_unix > (SELECT MAX(ts_unix) - 3600 FROM wifi_associations) ORDER BY ts_unix DESC;"
```

Export to GIS software:
- Convert `.db` to CSV/GeoJSON
- Analyze in QGIS, ArcGIS, or ArcGIS Online
- Filter out known rescuer devices (Samsung, Garmin, etc.) before analysis

Example post-processing map:

![Example Resulting Map](https://drive.google.com/uc?export=view&id=1T93QwNfIaOQkOVWXHegm51w6KZ1dYIt0)

---

## 🛠 Troubleshooting

| Issue | Solution |
|-------|-----------|
| GPS not updating | Check `gpsd` status and cable; ensure antenna has sky view |
| BLE adapter missing | Check with `hciconfig`; verify adapter name in `settings.py` |
| WiFi adapter not found | Check `iwconfig`/`iw dev`; verify USB connection and drivers installed |
| Monitor mode not working | Check [WIFI_SETUP.md](WIFI_SETUP.md) for manual setup instructions |
| Permission denied on WiFi | WiFi scanning requires `sudo` for raw packet access |
| Database locked | Use backups created by supervisor instead of live file |
| High CPU load | Ensure Raspberry Pi 5 has adequate cooling and power supply |
| Service won't start | Check logs: `sudo journalctl -u btscanner-supervisor -n 50` |

---

## 🗺️ Roadmap

- ✅ GPS integration  
- ✅ Bluetooth scanning  
- ✅ WiFi probe/association capture  
- ✅ Manufacturer ID resolution  
- ✅ Systemd service management
- 🕓 Configurable SSID filtering  
- 🕓 Meshtastic telemetry for live updates  
- 🕓 On-device dashboard / map  
- 🕓 Export to GeoJSON and QGIS project

---

## 🤝 Contributing

Contributions are welcome!

1. Fork the repository  
2. Create a branch (`git checkout -b feature-xyz`)  
3. Commit changes with clear messages  
4. Submit a pull request  

All code should:
- Be compatible with Raspberry Pi OS (Python 3.9+)
- Use standard libraries (minimize heavy dependencies)
- Include clear comments or docstrings
- Work on both `main` and `wifi-scanner` branches as appropriate

---

## 🧾 License

This project is licensed under the **Apache License 2.0**.  
© 2025 **Grupa Ratownictwa PCK Poznań**

See [`LICENSE`](LICENSE) for full text.

---

## ⚠️ Disclaimer

This tool is intended to **assist** SAR operations — it does **not replace** certified systems or professional procedures.  
Always operate under proper authorization and in compliance with local regulations.

---

## 🙏 Acknowledgements

Developed by **Grupa Ratownictwa PCK Poznań**  
Thanks to the maintainers of:
- `bleak` for Bluetooth scanning  
- `scapy` for WiFi packet capture
- `gpsd` for GPS data  
- The Bluetooth SIG for public manufacturer databases  
- Raspberry Pi Foundation for the hardware platform
