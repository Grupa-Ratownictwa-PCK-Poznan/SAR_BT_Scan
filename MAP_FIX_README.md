# Map Rendering Fix - Instructions

## Problem Fixed
The map was not displaying GPS coordinates even though they existed in the database.

## Root Causes (Now Fixed)
1. **Missing heat.js library** - The Leaflet.heat plugin was not loaded, which is required for L.heatLayer()
2. **Undeclared heatmapLayer variable** - The variable was used but never declared, causing potential scoping issues
3. **Frontend fixes applied to web_ui/index.html**:
   - Added: `<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet.heat/0.2.0/leaflet-heat.min.js"></script>`
   - Added: `let heatmapLayer = null;` in state initialization

## How to Use Your Real Database

When running the scanner on your system:

### Option 1: Default Production Path (Recommended)
The app automatically looks for: `/home/grpck/results.db`
- No configuration needed
- Works when you run the scanner normally

### Option 2: Development Environment
If the production path doesn't exist, the app tries:
1. `/tmp/test_results.db` 
2. `./test_results.db` 

### Option 3: Custom Database Location
If your database is elsewhere, modify the fallback paths in:
- File: `storage.py` (lines 11-15)
- File: `web_ui/app.py` (lines 44-48)

## Map Features
✓ Shows GPS coordinates with heatmap intensity based on signal strength (RSSI)
✓ Color gradient: blue (weak) → cyan → lime → yellow → red (strong)
✓ Automatically zooms to fit all points
✓ Updates when you filter by time, MAC, SSID, or RSSI

## Database Schema Requirements
The heatmap queries the `sightings` and `wifi_associations` tables:

```sql
-- Sightings (BT devices)
SELECT lat, lon, rssi FROM sightings 
WHERE lat IS NOT NULL AND lon IS NOT NULL

-- WiFi Associations  
SELECT lat, lon, rssi FROM wifi_associations
WHERE lat IS NOT NULL AND lon IS NOT NULL
```

## Testing
Run the create_test_db.py script to generate test data:
```bash
python3 create_test_db.py
```

This creates `/tmp/test_results.db` with sample GPS points in London and Paris.

## Git Commits
- **b2df52c**: Fix - Add missing heat.js library and declare heatmapLayer variable
- **dd63e6b**: Fix - Add database fallback paths for development
