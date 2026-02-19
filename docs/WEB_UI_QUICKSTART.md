# SAR Scanner Web UI - Quick Start Guide

## 30-Second Setup

### 1. Install Dependencies
```bash
pip install fastapi uvicorn
```

### 2. Start the Scanner
```bash
python main.py
```

Look for this message:
```
✓ Web UI started at http://localhost:8000
```

### 3. Open in Browser
Navigate to: **http://localhost:8000**

## Dashboard Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    SAR SCANNER UI                            │
├────────────────────────┬──────────────────────────────────┤
│                        │                                   │
│  SIDEBAR (550px)       │         MAIN CONTENT             │
│                        │                                   │
│  • Time                │  ┌──────────────────────────┐    │
│  • Status              │  │                          │    │
│  • Stats               │  │       HEATMAP MAP        │    │
│  • Filters             │  │                          │    │
│  • Tables (600px tall) │  │  (GPS color-coded pts)   │    │
│  • Update OUI Button   │  │                          │    │
│  • Map Type            │  └──────────────────────────┘    │
│                        │                                   │
└────────────────────────┴──────────────────────────────────┘
```

## Key Features at a Glance

| Feature | Location | Purpose |
|---------|----------|---------|
| **Live Time** | Top of sidebar | Current UTC time |
| **GPS Fix** | Status panel | Shows "3D/2D" if fixed or "NO FIX" |
| **Satellites** | Status panel | Number of satellites (need 4+ for good fix) |
| **Scan Mode** | Status panel | What's running: "bt", "wifi", or "both" |
| **WiFi Monitor** | Status panel | "ON" = monitor mode active, "OFF" = not running |
| **Device Counts** | Stats panel | Total devices captured |
| **BT Devices** | Table tab 1 | Bluetooth devices with manufacturer and notes |
| **BT Sightings** | Table tab 2 | Individual BT signals (with RSSI bars) |
| **WiFi Devices** | Table tab 3 | WiFi devices with vendor and device type |
| **WiFi Assoc** | Table tab 4 | Association attempts to SSIDs |
| **Mac Filter** | Filters | Search for specific device MAC |
| **SSID Filter** | Filters | Search for WiFi networks (WiFi Assoc tab) |
| **RSSI Sliders** | Filters | Show only strong/weak signals |
| **Hours Filter** | Filters | Show only recent N hours of data |
| **Update OUI** | Sidebar | Refresh IEEE vendor database |
| **Heatmap Map** | Right side | GPS position heatmap |
| **Map Type** | Bottom sidebar | Switch: BT / WiFi / Both |

## Common Tasks

### Update WiFi Vendor Database

1. Click **"Update OUI Database"** button in the sidebar
2. Wait for confirmation message
3. Vendor data will refresh from IEEE registry
4. Run "Analyze Confidence" to apply new data

### Find a Specific Device

1. Click the **BT Devices** or **WiFi Devices** tab
2. Enter MAC address in the **Mac Filter** field
3. Results update instantly
4. For WiFi devices, check the **Vendor** and **Type** columns for manufacturer info

### View Strong Signals Only

1. Go to **BT Sightings** or **WiFi Assoc** tab
2. Set **RSSI Min** slider to -70 (or adjust as needed)
3. Table shows only near devices

### Remove Startup Noise

1. Choose your data tab
2. Set **Recent Hours** to 1 (or whatever duration you want)
3. This removes the first measurements when scanner was starting

### See WiFi Hotspots

1. Click **Both** button in Map Type (bottom sidebar)
2. Map shows heatmap with GPS locations
3. Red areas = concentrated devices
4. Green areas = single devices

### Filter by Network

1. Go to **WiFi Assoc** tab
2. Enter SSID name in **SSID Filter** (e.g., "rescue")
3. See all devices trying to connect to that network

## Troubleshooting

### "Can't connect to http://localhost:8000"

**Problem**: Web UI isn't responding

**Solution**:
1. Check if it's enabled: Look for error in main.py output
2. If disabled: Change `WEB_UI_ENABLED = True` in settings.py
3. If port in use: Change `WEB_UI_PORT = 8080` in settings.py

### "GPS Fix" shows "NO FIX"

**Problem**: GPS not locked

**Solution**:
1. If you just started: Wait 30-60 seconds for GPS to acquire satellites
2. Check GPS device is connected and powered
3. Ensure clear sky view if using outdoor GPS

### Map shows no data

**Problem**: Heatmap empty

**Solution**:
1. Ensure GPS has a fix (shows "3D" or "2D")
2. Wait for scanner to capture sightings
3. Try switching map type (BT/WiFi/Both)
4. Check Recent Hours filter isn't too restrictive

### Data table empty

**Problem**: No results in table

**Solution**:
1. Wait for scan to run (takes a few seconds)
2. Check filter isn't too restrictive
3. Verify scan mode shows something is running
4. Try clearing all filters

## Keyboard Shortcuts

- **F12** - Open browser DevTools (for debugging)
- **Ctrl/Cmd +** - Zoom in
- **Ctrl/Cmd -** - Zoom out
- **Ctrl/Cmd 0** - Reset zoom

## Configuration Tips

### For High-Traffic Areas (Many Devices)

Add to settings.py:
```python
WEB_UI_REFRESH_INTERVAL = 2.0  # Update every 2 seconds instead of 1
```

This reduces server load when many devices are present.

### For Local-Only Access

Edit settings.py:
```python
WEB_UI_HOST = "127.0.0.1"  # Only accessible from this computer
```

### For Remote Access

Edit settings.py:
```python
WEB_UI_HOST = "0.0.0.0"  # Accessible from any IP on network
WEB_UI_PORT = 8000
```

Then access from another computer with:
```
http://<scanner-ip>:8000
```

## Data Refresh Rates

- **Live Time**: Every 1 second (always live)
- **Statistics**: Every second via WebSocket
- **Tables**: Refresh when you click filter or every 5 seconds automatically
- **WiFi Vendor Data**: Updated on-demand via "Update OUI Database" button
- **Map**: Every 5 seconds automatically
- **Status Indicators**: Every WebSocket update (~1 second)

## What Happens When Scanner Stops?

1. Scanners stop capturing data
2. Database remains intact
3. Web UI still shows historical data
4. Restart scanner with `python main.py` to resume capture

## Example Workflow

```
1. Start scanner:
   $ python main.py
   ✓ Web UI started at http://localhost:8000

2. Open browser:
   http://localhost:8000

3. Wait 30 seconds for GPS fix
   (Status panel shows 3D/2D when fixed)

4. Monitor stats panel as servers collect devices

5. Switch to WiFi Assoc tab to see network attempts

6. Look at heatmap to see spatial distribution

7. Use filters to deep-dive into specific signals

8. Check RSSI bars to identify signal strength patterns
```

## Performance Notes

- Web UI uses negligible resources when idle
- Database queries are optimized with indexes
- WebSocket updates are throttled
- Can safely run 24/7 on low-power hardware

## Need More Help?

- **Detailed Docs**: See `web_ui/README.md`
- **Implementation Details**: See `WEB_UI_IMPLEMENTATION.md`
- **API Reference**: See `/api/status` in browser (JSON)

## Quick Disable

If web UI interferes with other services:

Edit settings.py:
```python
WEB_UI_ENABLED = False  # Won't start or bind to any port
```

Restart scanner - no port will be used.

---

**Happy scanning!** 🗺️📡
