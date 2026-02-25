# SAR Scanner Web UI

A modern, responsive web dashboard for the SAR BT+WiFi Scanner with real-time data visualization, GPS status monitoring, and interactive heatmap overlay.

## Features

- **Live Dashboard**
  - Real-time clock display
  - GPS fix status and satellite count indicators
  - Scanner mode display (BT, WiFi, or Both)
  - WiFi monitor mode status indicator
  - **Dark/Light theme toggle** for comfortable viewing in any lighting

- **Live Statistics**
  - Global device and sighting counts
  - Auto-updating via WebSocket connection

- **Data Tables with Advanced Filtering**
  - BT Devices: MAC, Name, Manufacturer, Last Seen, Confidence, Notes
  - BT Sightings: Signal strength (RSSI), GPS coordinates
  - WiFi Devices: MAC, Vendor, Device Type, Last Seen, Confidence, Notes
  - WiFi Association Requests: MAC, SSID, Signal Strength
  - Filters: MAC address, SSID, RSSI range, Time window (0-24 hours), **Confidence score range**
  - Time filtering with dual sliders to exclude noisy scan start/end periods

- **Interactive Device Details**
  - Click any device row to open detailed popup
  - View all device information, associated SSIDs
  - **Edit analyst notes** directly in the popup
  - **"Analyze Location"** button for triangulation

- **Device Triangulation Page**
  - Movement analysis (MOVING/STATIONARY)
  - Location clusters visualization
  - Path tracking on interactive map
  - Estimated primary location with Google Maps link

- **Interactive Heatmap**
  - GPS-based spatial visualization
  - Color-coded intensity based on signal strength
  - Switchable layers: BT, WiFi associations, or Both
  - Automatic zoom-to-bounds when data is available
  - Leaflet.js-based mapping with OpenStreetMap tiles
  - **Offline fallback** with grid pattern background
  
- **WiFi Device Enrichment**
  - Automatic vendor lookup using IEEE OUI database (38,904 entries)
  - Device type heuristics (phone, network, iot, other)
  - Update OUI Database button for refreshing vendor data
  - OUI endpoint for on-demand database updates
  
- **Real-time WebSocket Updates**
  - Live data streaming without page refresh
  - Configurable update interval (default: 1 second)

## Installation

### Prerequisites

- Python 3.7+
- pip or conda

### Install Dependencies

The web UI requires FastAPI and Uvicorn. Install with:

```bash
pip install fastapi uvicorn
```

Or if you're using conda:

```bash
conda install -c conda-forge fastapi uvicorn
```

## Configuration

Edit `settings.py` to control the web UI:

```python
# Web UI configuration
WEB_UI_ENABLED = True        # Set to False to disable web interface
WEB_UI_HOST = "0.0.0.0"     # Listen on all interfaces
WEB_UI_PORT = 8000          # Local port for web UI
WEB_UI_REFRESH_INTERVAL = 1.0  # Seconds between live updates
```

### Settings Details

- **WEB_UI_ENABLED**: Toggle the entire web UI on/off. If disabled, the server won't start and won't bind to any port.
- **WEB_UI_HOST**: 
  - `"0.0.0.0"` - Listen on all network interfaces (accessible from network)
  - `"127.0.0.1"` - Listen only on localhost (local access only)
  - `"192.168.1.100"` - Listen on specific interface
- **WEB_UI_PORT**: HTTP port (default 8000)
- **WEB_UI_REFRESH_INTERVAL**: WebSocket update frequency in seconds

## Usage

When you start the scanner with `main.py`, the web UI automatically starts (if enabled):

```bash
python main.py
```

Look for the startup message:

```
✓ Web UI started at http://localhost:8000
```

### Accessing the Dashboard

Open your browser and navigate to:

- **Local access**: `http://localhost:8000`
- **Network access**: `http://<scanner-ip>:8000`

Replace `<scanner-ip>` with the IP address of the device running the scanner.

## Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  🕐 15:42:38                              [☀️ Theme] [ℹ️ About] [⚙️ Settings] │
├──────────────────────────────║──────────────────────────────────────────────┤
│  SIDEBAR (resizable)        ║                MAP AREA                       │
│ ┌─────────────────────────┐ ║  ┌──────────────────────────────────────────┐ │
│ │ GPS: 3D Fix ✓  12 sats  │ ║  │                                          │ │
│ │ Mode: Both   WiFi: ON   │ ║  │      🔴🟡🟢  GPS Heatmap                 │ │
│ └─────────────────────────┘ ║  │         (OpenStreetMap tiles)            │ │
│ ┌─────────────────────────┐ ║  │                                          │ │
│ │ BT Devices:     125     │ ║  │   Click any point for details            │ │
│ │ WiFi Devices:    89     │ ║  │                                          │ │
│ │ BT Sightings:  2,341    │ ║  │                                          │ │
│ │ WiFi Assoc:    1,567    │ ║  │                                          │ │
│ └─────────────────────────┘ ║  └──────────────────────────────────────────┘ │
│ ┌─────────────────────────┐ ║                                               │
│ │ [🔍 MAC Filter    ]     │ ║  Map Controls:                                │
│ │ [🔍 SSID Filter   ]     │ ║  [BT Only] [WiFi Only] [Both]                │
│ │ RSSI: ─●────── -60 dBm  │ ║                                               │
│ │ Confidence: ──●── 50%   │ ║                                               │
│ └─────────────────────────┘ ║                                               │
│ ┌─────────────────────────┐ ║                                               │
│ │ [BT Devices] [BT Sight] │ ║                                               │
│ │ [WiFi Dev] [WiFi Assoc] │ ║                                               │
│ │ ────────────────────────│ ║                                               │
│ │ MAC      │ Name │ Conf  │ ║                                               │
│ │ AA:BB:.. │ iPho │  72   │ ║                                               │
│ │ 11:22:.. │ Fitb │  35   │ ║                                               │
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

### Left Sidebar

1. **Live Time**: Current time in HH:MM:SS format (UTC)

2. **Status Indicators**:
   - **GPS Fix**: Shows fix status (3D/2D) or "NO FIX" (red)
   - **Satellites**: Number of satellites used for fix
   - **Scan Mode**: Current mode (bt, wifi, both)
   - **WiFi Monitor**: ON/OFF status of monitor mode

3. **Statistics**:
   - Real-time counts of devices and sightings
   - Updated via WebSocket

4. **Filters**:
   - MAC filter (substring match)
   - SSID filter (for WiFi associations)
   - RSSI range slider (-100 to 0 dBm)
   - **Confidence range slider** (0-100%)
   - Time presets (All/1h/24h/Custom)

5. **Data Tables**:
   - Tab-based view with 4 table types
   - **Click any row** to open detailed device popup
   - Highlighted rows for devices with notes

6. **Action Buttons**:
   - Download DB - Export database file
   - Purge DB - Clear data (with backup)
   - Analyze Confidence - Run scoring algorithm
   - Update OUI Database - Refresh vendor data

7. **Theme Toggle**: Switch between light (☀️) and dark (🌙) modes

### Main Content Area

**Heatmap**: Interactive map with GPS-based visualization
- Click and drag to pan
- Use mouse wheel to zoom
- Green/Yellow/Red colors indicate signal strength (strong to weak)
- Markers cluster at higher zoom levels (default Leaflet behavior)

## Filtering

### MAC Address Filter
- Works for all data types
- Substring matching (partial MAC addresses work)
- Example: `A1:2B:` matches all MACs starting with that prefix

### SSID Filter
- Only available for WiFi Association table
- Substring matching
- Example: Search `HOME` finds "HOME_NET", "MY_HOME_WIFI", etc.

### RSSI Range
- Dual sliders: minimum and maximum signal strength
- Range: -100 dBm (weakest) to 0 dBm (strongest)
- Useful for filtering out distant devices

### Time Window
- Filter last N hours of data
- 0 = All available data
- 1 = Last 1 hour
- 24 = Last 24 hours
- **Use case**: Exclude noisy start/end recording periods during SAR operations

## API Endpoints

The web UI backend provides REST API endpoints for advanced integration:

### Status
- `GET /api/status` - Current GPS and scanner status

### Data Queries
- `GET /api/bt/devices` - List BT devices
- `GET /api/bt/sightings` - BT sightings with filters
- `GET /api/wifi/devices` - List WiFi devices (includes vendor, device_type, notes)
- `GET /api/wifi/associations` - WiFi association requests with filters
- `GET /api/map/heatmap` - Heatmap data for map visualization

### Triangulation
- `GET /api/triangulate/{mac}` - Full triangulation analysis for a device
- `GET /triangulate` - Triangulation page (HTML)

### Confidence Analysis
- `POST /api/confidence/analyze` - Run confidence scoring algorithm
- `POST /api/confidence/apply` - Apply confidence scores to database

### Notes Management
- `POST /api/bt/devices/{mac}/notes` - Update BT device notes
- `POST /api/wifi/devices/{mac}/notes` - Update WiFi device notes

### Database Management
- `POST /api/oui/update` - Trigger OUI database update from IEEE registry
- `GET /api/db/download` - Download database file
- `POST /api/db/purge` - Clear database (creates backup first)

### WebSocket
- `WS /ws/live` - Live data stream with updates every `WEB_UI_REFRESH_INTERVAL` seconds

## Architecture

```
Scanner System (main.py)
├── BT Scanner (scanner.py)
├── WiFi Scanner (wifi_scanner.py)
├── GPS Client (gps_client.py)
└── Database (storage.py, results.db)
      ↓
   [Shared Database]
      ↓
Web UI Server (web_ui/app.py)
├── FastAPI Backend (async, multithreaded)
├── WebSocket Server
└── REST API
      ↓
   [HTTP/WebSocket]
      ↓
Frontend (web_ui/index.html)
├── Leaflet Maps (heatmap)
├── Data Tables
├── Real-time Updates
└── Browser Client
```

## Connection Points

As designed, the web UI only connects to:

1. **settings.py** - Configuration (port, host, enabled flag, refresh interval)
2. **results.db** - Read-only database queries
3. **gps_client.py** - GPS status and location information
4. **main.py** - Scanner mode state (passed to web app on startup)

## WiFi Device Enrichment Details

### Vendor Lookup (IEEE OUI)
When analyzing WiFi devices, the system performs IEEE OUI (Organizationally Unique Identifier) lookups:

- **Source**: IEEE Organizationally Unique Identifier database
- **Method**: MAC address prefix (first 3 octets) lookup
- **Coverage**: 38,904 vendor entries
- **Update Frequency**: Pull latest data anytime via "Update OUI Database" button
- **Field**: `device_type.vendor_name` stored in wifi_devices table

### Device Type Heuristic
Based on vendor and MAC patterns, the system estimates device category:

- **phone**: Mobile devices and smartphones
- **network**: Network equipment, routers, access points
- **iot**: IoT devices, sensors, smart home
- **other**: Unclassified devices

### Analyst Notes
Both BT and WiFi device tables include a `notes` column for analyst annotations:

- Free text field for custom observations
- Persists across sessions
- Appears in exports and reports
- Updated via web UI inline editing (future feature)

## Implemented Features

The following features are now available:

- **✅ Dark/Light Theme Toggle**
  - Switch between light and dark modes
  - Comfortable viewing in any lighting condition
  - Persists across sessions

- **✅ Interactive Device Details**
  - Click device rows to open popup
  - View complete device information
  - Edit and save analyst notes
  - One-click triangulation

- **✅ Device Triangulation**  
  - Movement analysis (MOVING/STATIONARY)
  - Location clustering
  - Path visualization
  - Estimated primary location
  - Google Maps integration

- **✅ Confidence Filtering**
  - Filter by confidence score range
  - Quickly focus on high-priority targets
  - Hide known SAR team equipment

- **✅ Notes Editing**
  - Edit notes directly in device popup
  - Notes persist in database
  - Highlighted rows for devices with notes

## Future Enhancements

The following features are planned for future versions:

- **Basic Authentication**
  - Username/password login
  - Session management
  - Configurable in settings.py

- **Advanced Visualization**
  - Time-series graphs of signal strength
  - Signal strength gradient maps

- **Export Features**
  - CSV export of filtered data
  - Map snapshots
  - GeoJSON export

- **Multi-Scanner Support**
  - Coordinate multiple scanners
  - Merge data from different devices

## Troubleshooting

### Port Already in Use

If port 8000 is already in use, change `WEB_UI_PORT` in settings.py:

```python
WEB_UI_PORT = 8080  # Use 8080 instead
```

### Web UI Not Responding

1. Check if it's enabled: `WEB_UI_ENABLED = True` in settings.py
2. Verify FastAPI/Uvicorn is installed: `pip install fastapi uvicorn`
3. Check main.py startup output for error messages
4. Try accessing `http://localhost:8000/api/status` to test the backend

### Map Shows "No Data"

- Ensure GPS is working and has a fix
- Check that devices are being captured by the scanners
- Verify database has sightings with GPS coordinates

### Data Not Updating

1. Check WebSocket connection: Open browser console (F12), check for errors
2. Verify GPS client is working with: `gc.get_gps_status()`
3. Increase `WEB_UI_REFRESH_INTERVAL` if system is under heavy load

## Performance Notes

- The web UI uses efficient database queries with pagination
- Default limit: 100-500 records per query (adjustable)
- WebSocket updates are rate-limited to prevent overwhelming the server
- Database indexes on timestamp and MAC address for fast filtering

## Security Notes

- **No authentication** by default (as requested)
- Runs on local network - consider network isolation
- Database is read-only from web UI
- Future: Basic auth will be added as optional feature

## Files

- `web_ui/app.py` - FastAPI backend server with API endpoints
- `web_ui/index.html` - Frontend dashboard (HTML/CSS/JavaScript)
- `web_ui/__init__.py` - Module initialization
- `settings.py` - Configuration (added settings for web UI)
- `main.py` - Modified to launch web UI server

## Requirements

- Python 3.7+
- fastapi
- uvicorn
- (existing scanner requirements: bleak, scapy, gps, etc.)

## License

Same as main SAR Scanner project
