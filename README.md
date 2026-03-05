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
- **WiFi vendor identification** (IEEE OUI database lookup) with device type heuristics
- **GPS integration** — coordinates and time tagging for all detections
- **SQLite storage** with optimized schema and WAL mode
- **Automatic manufacturer resolution** — Bluetooth SIG company IDs + WiFi OUI vendors
- **Expanded device type classification** — identifies phones, routers, wearables, headphones, hearing aids, pacemakers, insulin pumps, drones, SAR devices, IoT, TVs, home appliances, civil infrastructure, and more using BLE service UUIDs, device names, OUI vendors, WiFi SSIDs, and heuristics
- **Analyst notes** — add custom annotations to Bluetooth and WiFi devices
- **Dual-mode operation** — scan BT only, WiFi only, or both simultaneously
- **Supervisor watchdog** — keeps scanner running, creates timestamped database backups
- **Configurable paths and adapter names** via `settings.py`
- **Device triangulation** — analyze device location and movement patterns
- **Confidence scoring** — automatic scoring to differentiate SAR team vs. potential targets
- **Web UI with dark/light themes** — modern responsive dashboard with theme toggle
- **BLE GATT publisher** — broadcast sightings to companion apps (optional)

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
├── wifi_oui_lookup.py         # IEEE OUI vendor database (38,904 entries)
├── freeze_wifi_oui.py         # Utility to update OUI database from IEEE registry
├── confidence_analyzer.py     # Device confidence scoring algorithm
├── device_type_classifier.py  # Expanded device type classification (21 categories)
├── triangulation.py           # Device location and movement analysis
├── ble_protocol.py            # BLE GATT protocol definitions
├── ble_publisher.py           # BLE GATT sighting broadcaster
├── device_whitelist.txt       # SAR team equipment MACs (excluded from analysis)
├── configs/
│   ├── btscanner-supervisor       # Environment file (symlink to /etc/default/)
│   ├── btscanner-supervisor.service  # Systemd unit file
│   └── logtorate.d-btscanner-supervisor # Log rotation config
├── web_ui/
│   ├── app.py                 # FastAPI web server
│   ├── index.html             # Main dashboard (live view, heatmap)
│   ├── triangulation.html     # Device triangulation analysis page
│   └── mac_utils.py           # MAC address utilities
├── docs/                      # Documentation folder
│   ├── CONFIDENCE_ANALYZER.md # Confidence scoring algorithm
│   ├── TRIANGULATION.md       # Device triangulation documentation
│   ├── WEB_UI_QUICKSTART.md   # Web dashboard quick start
│   ├── WEB_UI_README.md       # Full web UI documentation
│   ├── WIFI_SETUP.md          # WiFi adapter setup guide
│   └── ...                    # Additional technical docs
├── USER_GUIDE.md              # User guide (English)
├── USER_GUIDE_PL.md           # User guide (Polish)
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

**Optional** (for BLE GATT publishing to companion app):
```bash
sudo apt install -y python3-dbus python3-gi
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
See [WIFI_SETUP.md](docs/WIFI_SETUP.md) for detailed instructions on enabling monitor mode on your USB WiFi adapter.

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

# Database configuration
CLEAN_DB_ON_STARTUP = False    # Set True to delete DB on each supervisor start
                               # When False, data persists and can be managed via web UI
USB_BACKUP_ENABLED = False     # Set True to enable automatic database backups to USB

# Web UI configuration
WEB_UI_ENABLED = True          # Set to False to disable web interface
WEB_UI_HOST = "0.0.0.0"        # Listen on all interfaces
WEB_UI_PORT = 8000             # Local port for web UI
WEB_UI_REFRESH_INTERVAL = 1.0  # Seconds between live updates (WebSocket)

# Confidence Analyzer configuration
HQ_LATITUDE = None             # Staging area latitude (auto-detect if None)
HQ_LONGITUDE = None            # Staging area longitude (auto-detect if None)
HQ_RADIUS_METERS = 100         # Devices seen only near HQ get lower confidence
DEVICE_WHITELIST_FILE = "device_whitelist.txt"  # Team equipment MACs
SESSION_GAP_SECONDS = 7200     # Gap (seconds) to start new session (2 hours)

# BLE GATT Publisher (optional companion app broadcast)
BLE_PUBLISH_ENABLED = False              # Enable to broadcast sightings via BLE
BLE_PUBLISH_INTERFACE = "hci0"           # Built-in BT interface (scanner uses hci1)
BLE_PUBLISH_DEVICE_NAME = "SAR-Scanner"  # Advertised BLE device name
BLE_PUBLISH_POLL_INTERVAL = 0.5          # Database poll interval in seconds
BLE_PUBLISH_MIN_RSSI = -100              # Default RSSI filter in dBm
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

## 🌐 Web UI Dashboard

A modern web-based dashboard provides **live monitoring** of scanning activity and data visualization with both **light and dark themes**.

### Accessing the Dashboard

Once the scanner is running, open your browser and navigate to:
```
http://localhost:8000
```

If running on a Raspberry Pi in your network:
```
http://<raspberry-pi-ip>:8000
```

### Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  🕐 15:42:38                              [☀️ Theme] [ℹ️ About] [⚙️ Settings] │
├──────────────────────────────║──────────────────────────────────────────────┤
│  SIDEBAR (resizable)        ║           MAIN MAP AREA                       │
│ ┌─────────────────────────┐ ║  ┌──────────────────────────────────────────┐ │
│ │ GPS: 3D Fix ✓  12 sats  │ ║  │                                          │ │
│ │ Mode: Both   WiFi: ON   │ ║  │      🔴🟡🟢  GPS Heatmap                 │ │
│ └─────────────────────────┘ ║  │         (OpenStreetMap tiles)            │ │
│ ┌─────────────────────────┐ ║  │                                          │ │
│ │ BT Devices:     125     │ ║  │   Click any point for device details:    │ │
│ │ WiFi Devices:    89     │ ║  │   • MAC address                          │ │
│ │ BT Sightings:  2,341    │ ║  │   • Signal strength                      │ │
│ │ WiFi Assoc:    1,567    │ ║  │   • Timestamp                            │ │
│ └─────────────────────────┘ ║  │   • Confidence score                     │ │
│ ┌─────────────────────────┐ ║  │                                          │ │
│ │ [🔍 MAC Filter    ]     │ ║  │                                          │ │
│ │ [🔍 SSID Filter   ]     │ ║  └──────────────────────────────────────────┘ │
│ │ RSSI: ─●────── -60 dBm  │ ║                                               │
│ │ Confidence: ──●── 50%   │ ║  Map Controls:                                │
│ │ [All] [1h] [24h] [Custom]│ ║  [BT Only] [WiFi Only] [Both]               │
│ └─────────────────────────┘ ║                                               │
│ ┌─────────────────────────┐ ║                                               │
│ │ [BT Dev][BT Sight][WiFi]│ ║                                               │
│ │ ───────────────────────  │ ║                                               │
│ │ MAC       │ Name │ Conf │ ║                                               │
│ │ AA:BB:... │ iPho │  72  │ ║                                               │
│ │ 11:22:... │ Fitb │  35  │ ║                                               │
│ │ CC:DD:... │      │  88  │ ║                                               │
│ │ (click row for details) │ ║                                               │
│ └─────────────────────────┘ ║                                               │
│ ┌─────────────────────────┐ ║                                               │
│ │ 📥 Download DB          │ ║                                               │
│ │ 🗑️  Purge DB             │ ║                                               │
│ │ 📊 Analyze Confidence   │ ║                                               │
│ │ 🔄 Update OUI Database  │ ║                                               │
│ └─────────────────────────┘ ║                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Dashboard Features

#### 📊 **Left Sidebar Panel** (resizable with drag divider)
- **GPS Status**: Shows fix status, satellites, HDOP, and last GPS coordinate
- **Scanner Mode**: Current scan mode (Bluetooth, WiFi, or Both)
- **WiFi Monitor**: Active WiFi scanner status
- **Live Statistics**: 
  - Total BT devices
  - Total WiFi devices
  - Total BT sightings
  - Total WiFi associations
- **Live Clock**: Real-time date and time with auto-updating display
- **Filtering Controls**: Filter by MAC address, RSSI, SSID, time range, confidence score
- **Database Management**:
  - **Download DB**: Export complete database file for backup/analysis
  - **Purge DB**: Clear all data with automatic backup creation (with confirmation)
  - **Analyze Confidence**: Run confidence scoring algorithm on all devices
  - **Update OUI Database**: Refresh WiFi vendor lookup data from IEEE registry
- **Theme Toggle**: Switch between light and dark mode (☀️/🌙)

#### 🗺️ **Interactive Map**
- **GPS Heatmap**: Visual representation of signal detections on OpenStreetMap
- **Color Gradient**: Intensity visualization (blue → cyan → green → yellow → red)
- **Point Details**: Click any marker for:
  - Device MAC address
  - SSID (for WiFi)
  - Signal strength (dBm)
  - Detection timestamp
  - Signal intensity percentage
  - Device type (WiFi/Bluetooth)
- **Map Controls**: Zoom, pan, layer selection (BT/WiFi/Both)
- **Offline Support**: Grid pattern fallback when tiles unavailable

#### 📋 **Data Tables** (scrollable, 600px height)
Four tabs display filtered, sortable data:
1. **BT Devices**: Unique Bluetooth devices with first/last seen times, manufacturer, confidence, and analyst notes
2. **BT Sightings**: Individual Bluetooth observations with RSSI and timestamps
3. **WiFi Devices**: Unique WiFi MAC addresses with vendor name, device type heuristic, confidence, and analyst notes
4. **WiFi Associations**: Networks devices attempted to join with GPS and timing

**Interactive Rows**: Click any device row to open a detailed popup with:
- Complete device information
- All associated SSIDs (for WiFi devices)
- Edit notes directly in the popup
- **"Analyze Location"** button for triangulation analysis

#### ⚙️ **Filter & Time Controls**
- **MAC Filter**: Search specific device by address
- **SSID Filter**: Find WiFi networks
- **RSSI Range**: Filter by signal strength (dBm)
- **Confidence Range**: Filter by confidence score (0-100)
- **Time Presets**:
  - All time
  - Last 1 hour
  - Last 24 hours
  - Custom date range

#### 🎨 **Theme Support**
The dashboard supports both light and dark themes:
- **Light Mode**: Red Cross branded colors with white background
- **Dark Mode**: Reduced eye strain for low-light conditions
- Toggle via the theme button in the header (☀️/🌙)

### Device Triangulation Page

Access the triangulation analysis for any device:
```
http://<scanner-ip>:8000/triangulate?mac=AA:BB:CC:DD:EE:FF
```

Or click **"Analyze Location"** in any device popup.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  📍 DEVICE TRIANGULATION - AA:BB:CC:DD:EE:FF            [← Back] [🔄 Refresh]│
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────┐  ┌──────────────────────────────────┐  │
│  │ DEVICE INFO                     │  │                                  │  │
│  │ MAC: AA:BB:CC:DD:EE:FF          │  │                                  │  │
│  │ Type: Bluetooth                 │  │       MOVEMENT MAP               │  │
│  │ Name: iPhone                    │  │                                  │  │
│  │ Manufacturer: Apple Inc.        │  │   🔵 First seen                  │  │
│  │ Confidence: 75%                 │  │   🟢 Last seen                   │  │
│  ├─────────────────────────────────┤  │   - - - Movement path            │  │
│  │ OBSERVATION SUMMARY             │  │   ● Location clusters            │  │
│  │ Total Sightings: 42             │  │                                  │  │
│  │ With GPS: 38                    │  │                                  │  │
│  │ First Seen: 08:15:32            │  │                                  │  │
│  │ Last Seen: 14:22:45             │  │                                  │  │
│  │ Duration: 6h 7m                 │  │                                  │  │
│  ├─────────────────────────────────┤  │                                  │  │
│  │ MOVEMENT ANALYSIS               │  └──────────────────────────────────┘  │
│  │ Status: MOVING                  │                                        │
│  │ Confidence: 78.5%               │  ┌──────────────────────────────────┐  │
│  │ Total Distance: 1523.4 m        │  │ SIGHTINGS TIMELINE              │  │
│  │ Avg Speed: 0.25 km/h            │  │                                  │  │
│  │ Max Speed: 4.43 km/h            │  │ 08:15 ●━━━━━━━━━━━━━●━━━━━━━●    │  │
│  ├─────────────────────────────────┤  │       Cluster 1    C2     C3     │  │
│  │ ESTIMATED PRIMARY LOCATION      │  │                                  │  │
│  │ Lat: 52.408100                  │  └──────────────────────────────────┘  │
│  │ Lon: 16.928500                  │                                        │
│  │ [🗺️ Open in Google Maps]        │                                        │
│  └─────────────────────────────────┘                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

The triangulation page shows:
- **Device Information**: MAC, type, name, manufacturer, confidence
- **Observation Summary**: Sighting counts, time range, duration
- **Movement Analysis**: Moving/stationary status, distance traveled, speed
- **Location Clusters**: Groups of nearby sightings
- **Interactive Map**: Visualizes movement path and cluster locations
- **Estimated Primary Location**: Most likely device position with Google Maps link

#### ℹ️ **About Button**
Link to this GitHub repository for documentation, issues, and contributions.

### WebSocket Live Updates

The dashboard uses WebSocket to receive **real-time** updates:
- Live counter refreshes (no page reload needed)
- GPS position updates
- Statistics streaming at 1-second intervals (configurable)

### Troubleshooting the Dashboard

**Map not showing points?**
- See [MAP_DEBUGGING_GUIDE.md](MAP_DEBUGGING_GUIDE.md) for detailed troubleshooting
- Points render as:
  - **Heatmap layer** if heat.js library loads successfully
  - **Colored circle markers** as fallback (guaranteed method)
- Check browser console (F12) for JavaScript errors

**Dashboard not loading?**
- Verify web UI is enabled: `WEB_UI_ENABLED = True` in `settings.py`
- Check port 8000 is not blocked: `lsof -i :8000`
- Ensure server is running: Check supervisor logs

**Filters not working?**
- Ensure database has data matching filter criteria
- Check that time range includes the data
- Verify GPS data exists for map (latitude/longitude required)

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
- (Optional) Clears the live database on startup based on `CLEAN_DB_ON_STARTUP` setting in `settings.py`:
  - **`CLEAN_DB_ON_STARTUP = False`** (default): Database is preserved across supervisor restarts. Use web UI's "Purge DB" button to manage data.
  - **`CLEAN_DB_ON_STARTUP = True`**: Database is deleted on each restart (legacy behavior)
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

## 📚 Additional Documentation

- [USER_GUIDE.md](USER_GUIDE.md) — Complete user guide for field operations
- [USER_GUIDE_PL.md](USER_GUIDE_PL.md) — Podręcznik użytkownika (Polish)
- [docs/WIFI_SETUP.md](docs/WIFI_SETUP.md) — Detailed WiFi adapter configuration and monitor mode setup
- [docs/CONFIDENCE_ANALYZER.md](docs/CONFIDENCE_ANALYZER.md) — Device confidence scoring algorithm
- [docs/DEVICE_TYPE_CLASSIFIER.md](docs/DEVICE_TYPE_CLASSIFIER.md) — Expanded device type classification
- [docs/TRIANGULATION.md](docs/TRIANGULATION.md) — Device triangulation and movement analysis
- [docs/WEB_UI_README.md](docs/WEB_UI_README.md) — Full web dashboard documentation
- [docs/WEB_UI_QUICKSTART.md](docs/WEB_UI_QUICKSTART.md) — Web dashboard quick start guide
- [docs/BLE_PROTOCOL.md](docs/BLE_PROTOCOL.md) — BLE GATT publisher protocol documentation
- [docs/MAP_DEBUGGING_GUIDE.md](docs/MAP_DEBUGGING_GUIDE.md) — Troubleshooting map visualization issues

---

## �🛠 Troubleshooting

| Issue | Solution |
|-------|-----------|
| GPS not updating | Check `gpsd` status and cable; ensure antenna has sky view |
| BLE adapter missing | Check with `hciconfig`; verify adapter name in `settings.py` |
| WiFi adapter not found | Check `iwconfig`/`iw dev`; verify USB connection and drivers installed |
| Monitor mode not working | Check [docs/WIFI_SETUP.md](docs/WIFI_SETUP.md) for manual setup instructions |
| Permission denied on WiFi | WiFi scanning requires `sudo` for raw packet access |
| Database locked | Use backups created by supervisor instead of live file |
| High CPU load | Ensure Raspberry Pi 5 has adequate cooling and power supply |
| Service won't start | Check logs: `sudo journalctl -u btscanner-supervisor -n 50` |
| Web UI not accessible | Check `WEB_UI_ENABLED = True`; verify port 8000 not blocked; check `lsof -i :8000` |
| Map shows no points | See [docs/MAP_DEBUGGING_GUIDE.md](docs/MAP_DEBUGGING_GUIDE.md) for detailed troubleshooting |
| Database export fails | Ensure database file has read permissions; try backup created by supervisor |
| Purge DB button not visible | Verify web UI is enabled and page reloads after each action |

---

## 🗺️ Roadmap

- ✅ GPS integration  
- ✅ Bluetooth scanning  
- ✅ WiFi probe/association capture  
- ✅ Manufacturer ID resolution  
- ✅ Systemd service management
- ✅ On-device web dashboard with live map visualization
- ✅ Database download and purge functionality
- ✅ Device confidence scoring algorithm
- ✅ Device triangulation and movement analysis
- ✅ Dark/light theme support
- ✅ Interactive device tooltips with notes editing
- ✅ BLE GATT publisher for companion apps
- ✅ Expanded device type classification (21 categories, BLE UUIDs + name + vendor + SSID heuristics)
- 🕓 Configurable SSID filtering  
- 🕓 Meshtastic telemetry for live updates  
- 🕓 Export to GeoJSON and QGIS project
- 🕓 Custom map tiles and offline mode
- 🕓 Multi-scanner coordination

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
