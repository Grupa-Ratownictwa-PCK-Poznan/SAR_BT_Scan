# SAR Scanner Web UI

A modern, responsive web dashboard for the SAR BT+WiFi Scanner with real-time data visualization, GPS status monitoring, and interactive heatmap overlay.

## Features

- **Live Dashboard**
  - Real-time clock display
  - GPS fix status and satellite count indicators
  - Scanner mode display (BT, WiFi, or Both)
  - WiFi monitor mode status indicator

- **Live Statistics**
  - Global device and sighting counts
  - Auto-updating via WebSocket connection

- **Data Tables with Advanced Filtering**
  - BT Devices: MAC, Name, Manufacturer, Last Seen, Notes
  - BT Sightings: Signal strength (RSSI), GPS coordinates
  - WiFi Devices: MAC, Vendor, Device Type, Last Seen, Notes
  - WiFi Association Requests: MAC, SSID, Signal Strength
  - Filters: MAC address, SSID, RSSI range, Time window (0-24 hours)
  - Time filtering with dual sliders to exclude noisy scan start/end periods

- **Interactive Heatmap**
  - GPS-based spatial visualization
  - Color-coded intensity based on signal strength
  - Switchable layers: BT, WiFi associations, or Both
  - Automatic zoom-to-bounds when data is available
  - Leaflet.js-based mapping with OpenStreetMap tiles
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

4. **Data Tables**:
   - Tab-based view with 4 table types
   - Advanced filtering options

5. **Map Display**: Button group to select heatmap type

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

### Database Management
- `POST /api/oui/update` - Trigger OUI database update from IEEE registry

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

## Future Enhancements

The following features are planned for future versions:

- **Basic Authentication**
  - Username/password login
  - Session management
  - Configurable in settings.py

- **Advanced Visualization**
  - Time-series graphs of signal strength
  - Device trajectory visualization
  - Signal strength gradient maps

- **Export Features**
  - CSV export of filtered data
  - Map snapshots
  - Report generation with enriched data

- **Device Management**
  - Inline notes editing in tables
  - Mark devices as known/unknown
  - Custom device labels/annotations
  - Threat level tagging

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
