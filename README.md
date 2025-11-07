# SAR_BT_Scan — Bluetooth Scanner for Search and Rescue (SAR)

**SAR_BT_Scan** is an open-source tool by **Grupa Ratownictwa PCK Poznań** designed to assist Search and Rescue (SAR) operations.  
It continuously scans Bluetooth Low Energy (BLE) beacons, tags them with GPS coordinates and timestamps, and stores the data in a local SQLite database for post-mission analysis and visualization.

---

## 🌍 Purpose

In SAR operations, missing persons often carry devices that emit Bluetooth signals — phones, smartwatches, fitness bands, etc.  
This project provides a **portable Bluetooth scanner** that moves with rescuers and records every detected signal with location and time.  
After the mission, the data can be reviewed to find potential devices belonging to the missing person.

---

## 🧩 Hardware Setup

The prototype has been successfully tested on:

| Component | Model / Notes |
|------------|---------------|
| **Host** | Raspberry Pi 5 (4 GB) with Raspberry Pi OS |
| **Bluetooth Adapter** | TP-Link UB500 Plus (Bluetooth 5.0, external antenna) |
| **GPS Receiver** | VK-162 USB GPS dongle |
| **Storage** | USB pendrive for safe data offload |
| **Power** | Powerbank (approx. 3 W draw — ~10 h runtime on 10 000 mAh) |

![Prototype](https://drive.google.com/uc?export=view&id=1jDb16UQ4cg9WnSK-n0fTD6O_-fwnG6FV)
![Prototype](https://drive.google.com/uc?export=view&id=1cIs_jqTanOg82i_qh1hnH-aQ7wgvCcVy)

---

## 🧠 Project Overview

### Main Features
- Real-time **Bluetooth beacon scanning** (BLE advertisements)
- **GPS integration** — coordinates and time tagging
- **SQLite storage** with optimized schema and WAL mode
- **Automatic manufacturer resolution** (Bluetooth SIG company IDs)
- **Supervisor watchdog** — keeps scanner running, creates timestamped database backups
- **Configurable paths and adapter names** via `settings.py`

### Repository Layout
```
SAR_BT_Scan/
├── main.py                 # Entry point: runs the scanner
├── scanner.py              # BLE scanning logic using bleak
├── gps_client.py           # GPSD client providing coordinates and UTC time
├── storage.py              # SQLite schema and write helpers
├── supervisor.py           # Watchdog that restarts scanner and backs up DB
├── settings.py             # Configuration (paths, adapter name, scanner ID)
├── bt_manufacturer_ids.py  # Bluetooth SIG company ID mappings
├── freeze_company_ids.py   # Utility to update company ID database
└── README.md               # This file
```

---

## ⚙️ Installation

### 1. System Requirements
- Raspberry Pi OS (Bookworm or later)
- Python 3.9+
- GPSD and BlueZ packages

### 2. System Setup
```bash
sudo apt update
sudo apt install -y python3 python3-pip bluez sqlite3 gpsd gpsd-clients python3-gps
```

### 3. Clone the Repository
```bash
git clone https://github.com/GRPCK-Poznan/SAR_BT_Scan.git
cd SAR_BT_Scan
```

### 4. Install Python Dependencies
```bash
pip install bleak
```

---

## ⚙️ Configuration

Edit `settings.py` to match your hardware setup:

```python
USB_STORAGE = "/mnt/pendrive"  # Path for DB backups
SD_STORAGE  = "/home/pi/"      # Live working directory
DB_FILE     = "results.db"

BLEAK_DEVICE = "hci1"          # BLE adapter (often hci1 for TP-Link UB500)
SCANNER_ID   = "Scanner_1"     # Identifier written to each DB record
```

### GPS Configuration
Ensure `gpsd` is active and configured to use your receiver (e.g. `/dev/ttyACM0`):

```bash
sudo systemctl enable gpsd
sudo systemctl start gpsd
cgps -s    # verify GPS fix
```

---

## ▶️ Running the Scanner

### Simple (foreground)
```bash
python3 main.py
```

### Recommended (supervised)
Run the supervisor, which restarts the scanner if it fails and performs automatic backups:

```bash
python3 supervisor.py
```

This will:
- Continuously scan BLE advertisements
- Write live data to the main database
- Periodically back up the DB to `/mnt/pendrive` as timestamped copies, e.g.  
  `2025-11-04-13-26-08-BTlog.db`

---

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
