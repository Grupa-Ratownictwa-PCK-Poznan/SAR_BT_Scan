# SAR Scanner Web UI - Implementation Summary

## Overview

A complete web-based dashboard for the SAR BT+WiFi Scanner has been implemented with the following architecture:

```
Scanner Backend          →    Database (SQLite)    ←    Web UI Server (FastAPI)
  (main.py)                   (results.db)              (web_ui/app.py)
                                                            ↓
                                                    Frontend Dashboard
                                                  (web_ui/index.html)
                                                      [Browser UI]
```

## What Was Created

### 1. Settings Configuration (`settings.py`)
Added new settings to control the web UI:
```python
WEB_UI_ENABLED = True        # Enable/disable the entire web UI
WEB_UI_HOST = "0.0.0.0"      # Bind address
WEB_UI_PORT = 8000           # HTTP port
WEB_UI_REFRESH_INTERVAL = 1.0  # WebSocket update frequency (seconds)
```

**Key Feature**: When `WEB_UI_ENABLED = False`, the web server won't be launched and won't bind to any port, preventing resource usage and port conflicts.

### 2. Web Server Backend (`web_ui/app.py`)
A FastAPI application providing:

**Core Components**:
- Database query functions for BT/WiFi data with filtering
- WebSocket connection manager for live updates
- Scanner state tracking (mode, WiFi monitor status)

**REST API Endpoints**:
- `GET /api/status` - GPS fix, satelli count, scanner mode
- `GET /api/bt/devices` - BT device list
- `GET /api/bt/sightings` - BT sightings with MAC/RSSI/time filters
- `GET /api/wifi/devices` - WiFi device list
- `GET /api/wifi/associations` - WiFi association requests with SSID/RSSI/time filters
- `GET /api/map/heatmap` - Heatmap data (GPS coordinates with intensity)
- `WS /ws/live` - WebSocket live updates

**Filtering Capabilities**:
- MAC address substring matching
- SSID substring matching
- RSSI range (dBm)
- Time window (hours back from now)
- Pagination with configurable limits

### 3. Frontend Dashboard (`web_ui/index.html`)
A modern, dark-themed web interface featuring:

**Dashboard Components**:

1. **Live Time Display**
   - Real-time UTC clock
   - Updated every second

2. **Status Indicators**
   - GPS Fix Status (3D/2D or NO FIX)
   - Satellite Count
   - Scanner Mode (bt/wifi/both)
   - WiFi Monitor Mode (ON/OFF)

3. **Live Statistics**
   - BT Device Count
   - WiFi Device Count
   - BT Sighting Count
   - WiFi Association Count
   - Auto-updates via WebSocket

4. **Data Tables** (Tab-based)
   - **BT Devices**: MAC, Name, Manufacturer, Last Seen, Notes
   - **BT Sightings**: MAC, RSSI (with visual bar), Timestamp
   - **WiFi Devices**: MAC, Vendor, Device Type, Last Seen, Notes
   - **WiFi Associations**: MAC, SSID, RSSI (with visual bar)

5. **Advanced Filters**
   - MAC Address: Works across all data types
   - SSID: WiFi associations only
   - RSSI Range: Dual sliders (-100 to 0 dBm)
   - Time Window: Recent N hours (0-24)

6. **Interactive Map**
   - Leaflet.js + OpenStreetMap
   - Heatmap layer with color-coded intensity
   - Switchable overlays: BT only, WiFi only, or Both
   - Auto-zoom to data bounds
   - Click/drag to pan, scroll to zoom

**Features**:
- Dark theme optimized for night SAR operations
- WebSocket connection for real-time updates
- Responsive layout (sidebar + main content)
- RSSI visualization bars with color gradient (red→yellow→green)
- Auto-reconnection on WebSocket disconnect

### 4. Module Integration (`web_ui/__init__.py`)
Helper module for standalone web UI testing (optional).

### 5. Main Integration (`main.py`)
Updated to:
- Import web UI settings
- Launch web server in background thread when enabled
- Display web UI URL at startup
- Pass scanner mode to web app
- Graceful error handling if FastAPI is not installed

## Connection Points (As Specified)

The web UI only connects to:

1. **`settings.py`** - Configuration reading
2. **`results.db`** (through `storage.py`) - Read-only database queries
3. **`gps_client.py`** - GPS status and location via module functions
4. **`main.py`** - Scanner mode state (passed on startup via `update_scanner_state()`)

**No other connections**: The web UI doesn't modify scanner behavior, hijack execution, or interact with WiFi/BT scanning modules.

## How It Works

### Startup Sequence

1. User runs `python main.py`
2. scanner initializes GPS, database, BT scanner, WiFi scanner
3. If `WEB_UI_ENABLED = True`:
   - FastAPI server starts in background thread
   - Binds to `WEB_UI_HOST:WEB_UI_PORT`
   - Prints "✓ Web UI started at http://localhost:8000"
4. Scanners begin collection
5. Web UI queries database and GPS in real-time

### Data Flow for Filtering Example

```
User enters MAC filter "A1:2B"
         ↓
JavaScript sends request to /api/bt/sightings?mac_filter=A1:2B&hours_back=1
         ↓
FastAPI query_sightings() builds SQL query:
  SELECT * FROM sightings 
  WHERE addr LIKE '%A1:2B%' 
  AND ts_unix >= NOW() - 3600
  ORDER BY ts_unix DESC LIMIT 500
         ↓
Results returned as JSON
         ↓
Frontend updates table with RSSI visualization
```

### Live Update via WebSocket

```
Every 1 second (configurable):
  Frontend connects to /ws/live
              ↓
  Server queries: GPS status, statistics, recent data
              ↓
  Sends JSON update via WebSocket
              ↓
  Frontend updates: indicators, stats, recent sightings
```

## Usage Instructions

### Installation (One-time)
```bash
pip install fastapi uvicorn
```

### Running
```bash
python main.py
```

### Accessing
- **Local**: `http://localhost:8000`
- **Network**: `http://<scanner-ip>:8000`

## Key Advantages

1. **Decoupled Design**
   - Web UI runs independently
   - Failure in web UI doesn't affect scanning
   - Easy to disable if not needed

2. **No Authentication (For Now)**
   - Simple deployment
   - Future-proof: Can add basic auth later without major refactoring

3. **Real-time Feedback**
   - WebSocket updates keep UI fresh
   - GPS fix feedback immediately visible
   - Device counts update live

4. **Powerful Filtering**
   - Time-window sliders remove noisy start/end data
   - RSSI filtering isolates strong/weak signals
   - MAC/SSID substring matching for quick searches

5. **WiFi Device Enrichment**
   - Automatic IEEE OUI (Organizationally Unique Identifier) vendor lookup
   - Device type heuristics (phone, network, iot, other)
   - Analyst notes field in both BT and WiFi device tables
   - "Update OUI Database" button for on-demand database refresh
   - `/api/oui/update` endpoint to trigger OUI data refresh

6. **Spatial Visualization**
   - Heatmap shows device density at GPS locations
   - Helps identify hotspots in SAR search areas
   - Switchable BT/WiFi overlays for comparison

## WiFi Enrichment Details

The system automatically enriches WiFi device data using the IEEE OUI database:

### OUI Database Integration
- **File**: `wifi_oui_lookup.py` - Contains 38,904 vendor mappings
- **Update Script**: `freeze_wifi_oui.py` - Fetches latest data from IEEE registry
- **Storage**: Vendor names stored in `wifi_devices.vendor_name` field
- **Device Type**: Heuristic guess stored in `wifi_devices.device_type` field

### Analyst Notes
- Both `devices.notes` (Bluetooth) and `wifi_devices.notes` (WiFi) columns
- Free-text field for analyst observations
- Persists across sessions and appears in exports

### UI Integration
- "Update OUI Database" button in sidebar triggers immediate refresh
- `/api/oui/update` endpoint runs `freeze_wifi_oui.py` subprocess
- Vendors displayed in WiFi Devices table
- Device type heuristic helps categorize MACs

## Performance Characteristics

- **Database Queries**: Paginated (100-500 records default)
- **WebSocket Updates**: Rate-limited to `WEB_UI_REFRESH_INTERVAL`
- **Memory**: Minimal impact on scanner system
- **CPU**: Single background thread for web server
- **Thread Safety**: Uses context managers and locks where needed

## Testing Checklist

After deployment, verify:

- [ ] Web UI disabled mode: `WEB_UI_ENABLED = False` prevents port binding
- [ ] Web UI enabled: Loads at `http://localhost:8000`
- [ ] GPS indicator updates with satellite count
- [ ] WiFi monitor mode shows correctly as ON/OFF
- [ ] BT sighting table shows RSSI bars with color gradient
- [ ] Time filter slider restricts data to selected hours
- [ ] MAC filter finds partial matches
- [ ] Heatmap loads with GPS data points
- [ ] Map layer switch works (BT/WiFi/Both)
- [ ] WebSocket reconnects after network interruption
- [ ] Statistics update in real-time
- [ ] WiFi Devices table shows Vendor and Device Type columns
- [ ] Notes column appears in both BT and WiFi tables
- [ ] "Update OUI Database" button visible in sidebar
- [ ] Wider sidebar (550px) and taller tables (600px) layout

## Future Enhancements (Planned)

- ✅ WiFi vendor identification via IEEE OUI (COMPLETED)
- ✅ Device type heuristics for WiFi (COMPLETED)
- ✅ Analyst notes columns (COMPLETED)
- ✅ UI layout improvements - wider sidebar and taller tables (COMPLETED)
- ✅ Update OUI Database button (COMPLETED)
- Basic authentication (username/password)
- Signal strength time-series graphs
- Device trajectory visualization
- CSV export
- Custom map overlays
- Threat level indicators
- Inline notes editing in tables

## File Structure

```
SAR_BT_Scan/
├── main.py (MODIFIED - starts web UI)
├── settings.py (MODIFIED - added web UI config)
├── storage.py
├── scanner.py
├── wifi_scanner.py
├── gps_client.py
└── web_ui/ (NEW)
    ├── __init__.py
    ├── app.py (FastAPI server)
    ├── index.html (Frontend dashboard)
    └── README.md (Detailed documentation)
```

## Dependency Management

The web UI gracefully handles missing dependencies:

```python
# If FastAPI/Uvicorn not installed:
try:
    from web_ui.app import app
except ImportError:
    print("⚠ Web UI dependencies not installed...")
    print("Install with: pip install fastapi uvicorn")
```

Scanner continues running even if web UI fails to start.

---

**Status**: ✅ Complete and Ready for Deployment

All requirements have been met:
- ✅ Web application separate from scanner
- ✅ Only connections: settings, database, GPS, main.py
- ✅ Configuration in settings.py to enable/disable
- ✅ Live preview of results
- ✅ GPS fix indicator
- ✅ Scanner mode indicator
- ✅ WiFi monitor mode status
- ✅ Local time display
- ✅ Filtered data tables (MAC, SSID, RSSI, time)
- ✅ Interactive map with heatmap
- ✅ BT/WiFi switchable overlay
- ✅ No authentication (future-ready for basic auth)
- ✅ WiFi vendor identification via IEEE OUI database
- ✅ Device type heuristics for WiFi devices
- ✅ Analyst notes columns for BT and WiFi devices
- ✅ Update OUI Database button with /api/oui/update endpoint
- ✅ Wider sidebar (550px) and taller tables (600px)
