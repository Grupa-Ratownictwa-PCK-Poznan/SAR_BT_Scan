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
├── main.py                 # Entry point: mode selector (BT/WiFi/both)
├── scanner.py              # BLE scanning logic using bleak
├── wifi_scanner.py         # WiFi probe capture using scapy
├── gps_client.py           # GPSD client providing coordinates and UTC time
├── storage.py              # SQLite schema and write helpers
├── supervisor.py           # Watchdog that restarts scanner and backs up DB
├── settings.py             # Configuration (paths, adapters, scan mode)
├── bt_manufacturer_ids.py  # Bluetooth SIG company ID mappings
├── freeze_company_ids.py   # Utility to update company ID database
├── WIFI_SETUP.md           # WiFi adapter setup guide
└── README.md               # This file
```

---

## ⚙️ Installation

### 1. System Requirements
- Raspberry Pi OS (Bookworm or later)
- Python 3.9+
- GPSD and BlueZ packages
 aircrack-ng wireless-tools
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
### 4. Install Python Dependencies
```bash
pip install bleak
```

---

## ⚙️ Configuration

# Storage paths
USB_STORAGE = "/mnt/pendrive"  # Path for DB backups
SD_STORAGE  = "/home/pi/"      # Live working directory
DB_FILE     = "results.db"

# Bluetooth configuration
BLEAK_DEVICE = "hci1"          # BLE adapter (often hci1 for TP-Link UB500)
SCANNER_ID   = "Scanner_1"     # Identifier written to each DB record

# Scanning mode and WiFi configuration
SCAN_MODE = "both"             # Options: "bt", "wifi", or "both"
WIFI_INTERFACE = "wlan0"       # USB WiFi adapter interface in monitor mode
KNOWN_WIFIS = []               # List of SSIDs to identify (empty = capture all)

BLEAK_DEVICE = "hci1"          # BLE adapter (often hci1 for TP-Link UB500)
SCANNER_ID   = "Scanner_1"     # Identifier written to each DB record
```

### GPS Configuration
Ensure `gpsd` is active and configured to use your receiver (e.g. `/dev/ttyACM0`):

```bBluetooth Only
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

### Supervised (Recommended)
Run the supervisor, which restarts the scanner if it fails and performs automatic backups:
Bluetooth Tables

**Table: `devices`** (BLE devices)
| Field | Description |
|--------|-------------|
| addr | Bluetooth MAC address |
| first_seen / last_seen | Unix timestamps |
| name | Device name |
| manufacturer_hex / manufacturer | Bluetooth SIG ID + readable name |

**Table: `sightings`** (BLE observations)
| Field | Description |
|--------|-------------|
| id | Auto-increment |
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

**Table: `wifi_devices`** (WiFi devices seen)
| Field | Description |
|--------|-------------|
| mac | WiFi MAC address |
| first_seen / last_seen | Unix timestamps |
| vendor | Vendor name (if available) |

**Table: `wifi_associations`** (WiFi networks devices tried to join)
| Field | WiFi adapter monitor mode** (if enabled)
  ```bash
  iwconfig wlan0  # Should show "Mode:Monitor"
  ```
- **Check GPS**
  ```bash
  cgps -s
  ```
- **Inspect collected data**
  ```bash
  sqlite3 /home/pi/results.db 'SELECT COUNT(*) FROM sightings;'
  sqlite3 /home/pi/results.db 'SELECT COUNT(*) FROM wifi_association
| rssi | Signal strength (dBm) |
| scanner_name | Identifier of scanning device=================is is to prevent the scanner from mixing data from various operations. If you boot the device multiple times in a single mission - no worries, you will still have all the database snapshots on the USB memory (unless you wipe it). This wipe was added because it's easier to clean up files from USB memory (you can connect to a computer with screen) than from the scanner itself.

At the end of the mission:
- Retrieve `.db` files from `/mnt/pendrive`.
- Analyze with examples:
  ```bash
  # All BLE devices
  sqlite3 results.db "SELECT addr, name, COUNT(*) FROM sightings GROUP BY addr ORDER BY COUNT(*) DESC LIMIT 20;"
  
  # All WiFi networks seen
  sqlite3 results.db "SELECT DISTINCT ssid FROM wifi_associations;"
  
  # Devices connecting to a specific network
  sqlite3 results.db "SELECT DISTINCT mac FROM wifi_associations WHERE ssid='Home_Network';"
  
  # Timeline of a single device
  sqlite3 results.db "SELECT datetime(ts_unix, 'unixepoch'), ssid, rssi, lat, lon FROM wifi_associations WHERE mac='AA:BB:CC:DD:EE:FF' ORDER BY ts_unix;"
  ```
- Export to GIS software (QGIS, ArcGIS) as CSV/GeoJSON

[BT] 00:1A:2B:3C:4D:5E - Device Name (RSSI: -65)
[WiFi] AA:BB:CC:DD:EE:FF -> Home_Network (RSSI: -45)
``rts the scanner if it fails and performs automatic backups:

```bash
python3 supervisor.py
```

ThWiFi adapter not found | Check `iwconfig`/`iw dev`; verify USB connection and drivers installed |
| Monitor mode not working | Run `sudo airmon-ng check kill` then `sudo airmon-ng start wlan0` |
| Permission denied on WiFi | WiFi scanning requires `sudo` for raw packet access |
| Database locked | Use backups created by supervisor instead of live file |
| High CPU load | Ensure Raspberry Pi 5 has adequate cooling and PSU |

For detailed WiFi setup help, see [WIFI_SETUP.md](WIFI_SETUP.md).
- Write live data to the main database
- PeBluetooth scanning  
- ✅ WiFi probe/association capture  
- ✅ Manufacturer ID resolution  
- 🕓 Configurable SSID filtering  
- 🕓 Meshtastic telemetry for live updates  
- 🕓 On-device dashboard / map  
- 🕓 Export to GeoJSON and QGIS project

## 🗃️ Data Structure

### Table: `devices`
| Field | Description |
|--------|-------------|
| addr | Bluetooth MAC address |
| first_seen / last_seen | Unix timestamps |
| name | Device name |
| manufacturer_hex / manufacturer | Bluetooth SIG ID + readable name |

### Table: `sightings`
| Field | Description |
|--------|-------------|
| id | Auto-increment |
| addr | MAC address |
| ts_unix / ts_gps | Time of sighting |
| lat / lon / alt | GPS coordinates |
| rssi | Signal strength (dBm) |
| tx_power | Transmit power (if available) |
| scanner_name | Identifier of scanning device |
| manufacturer | Vendor name |
| service_uuid | BLE service info |
| adv_raw | Optional raw advertisement data |

---

## 🧪 Verifying Operation

- **Check Bluetooth adapter**
  ```bash
  hciconfig
  bluetoothctl show
  ```
- **Check GPS**
  ```bash
  cgps -s
  ```
- **Inspect collected data**
  ```bash
  sqlite3 /home/pi/results.db 'SELECT COUNT(*) FROM sightings;'
  ```

---

## 📤 Data Offload & Analysis

Keep in mind - the supervisor will wipe the DB file on every service start. Thsi is to prevent the scanner from mixing data from various operations. If you boot the device multiple times in a single mission - no worries, you will still have all the database snapshots on the USB memory (unless you wipe it). This wipe was added because it's easier to clean up files from USB memory (you can connect to a computer with screen) than from the scanner itself.

At the end of the mission:
- Retrieve `.db` files from `/mnt/pendrive`.
- Analyze with:
  - QGIS or other GIS software (convert to GeoJSON/CSV)
  - Python notebooks or your own tools
- Filter out known rescuer devices (Samsung, Garmin, etc.) before analysis.

Example post-processing map:

![Example Resulting Map](https://drive.google.com/uc?export=view&id=1T93QwNfIaOQkOVWXHegm51w6KZ1dYIt0)

---

## 🛠 Troubleshooting

| Issue | Solution |
|-------|-----------|
| GPS not updating | Check `gpsd` status and cable; ensure antenna has sky view |
| BLE adapter missing | Check with `hciconfig`; correct adapter in `settings.py` |
| Database locked | Use backups created by supervisor instead of live file |
| High CPU load | Ensure Raspberry Pi 5 has adequate cooling and PSU |

---

## 🗺️ Roadmap

- ✅ GPS integration  
- ✅ Manufacturer ID resolution  
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
- Use standard libraries (avoid heavy dependencies)
- Include clear comments or docstrings

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
- `gpsd` for GPS data  
- The Bluetooth SIG for public manufacturer databases  
- Raspberry Pi Foundation for the hardware platform
