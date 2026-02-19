# Device Triangulation Module

The triangulation module analyzes all sightings for a specific device (identified by MAC address) to determine its location and movement patterns. It works with both Bluetooth and WiFi devices.

## Features

- **Location Clustering**: Groups nearby sightings into location clusters
- **Movement Analysis**: Determines if a device is stationary or moving
- **Path Visualization**: Generates timeline data for map visualization
- **Dual Interface**: Available as CLI tool and web application

## Usage

### Command Line Interface

```bash
# Basic analysis (formatted text output)
python triangulation.py AA:BB:CC:DD:EE:FF

# JSON output (for scripting/integration)
python triangulation.py AA:BB:CC:DD:EE:FF --json

# Specify custom database path
python triangulation.py AA:BB:CC:DD:EE:FF --db /path/to/results.db

# Save JSON to file
python triangulation.py AA:BB:CC:DD:EE:FF --json > analysis.json
```

### Web Interface

Access the triangulation page in your browser:

```
http://<scanner-ip>:8000/triangulate?mac=AA:BB:CC:DD:EE:FF
```

Or click the **"Analyze Location"** button in the device tooltip on the main dashboard.

### API Endpoint

```
GET /api/triangulate/{mac}
```

Returns JSON with full analysis results.

## Output

### Text Output (CLI)

```
============================================================
DEVICE TRIANGULATION ANALYSIS
============================================================

DEVICE INFORMATION
----------------------------------------
  MAC Address:    AA:BB:CC:DD:EE:01
  Device Type:    BT
  Name:           Device 1
  Manufacturer:   Apple Inc.
  Confidence:     75%

OBSERVATION SUMMARY
----------------------------------------
  Total Sightings:       42
  With GPS Location:     38
  First Seen:            2026-02-17 08:15:32
  Last Seen:             2026-02-17 14:22:45
  Observation Duration:  6h 7m

MOVEMENT ANALYSIS
----------------------------------------
  Status:                MOVING
  Confidence:            78.5%
  Total Distance:        1523.4 m
  Area Covered:          45231.2 sq m
  Average Speed:         0.07 m/s (0.25 km/h)
  Maximum Speed:         1.23 m/s (4.43 km/h)

LOCATION CLUSTERS
----------------------------------------
  Cluster #1:
    Center:     (52.406400, 16.925200)
    Sightings:  15
    Avg RSSI:   -62.3 dBm
    First Seen: 08:15:32
    Last Seen:  09:45:12

  Cluster #2:
    Center:     (52.408100, 16.928500)
    Sightings:  23
    ...

ESTIMATED PRIMARY LOCATION
----------------------------------------
  Latitude:  52.408100
  Longitude: 16.928500
  https://www.google.com/maps?q=52.4081,16.9285

============================================================
```

### JSON Output Structure

```json
{
  "mac": "AA:BB:CC:DD:EE:01",
  "device_type": "bt",
  "first_seen": 1771356932,
  "first_seen_str": "2026-02-17T08:15:32",
  "last_seen": 1771378965,
  "last_seen_str": "2026-02-17T14:22:45",
  "total_sightings": 42,
  "sightings_with_location": 38,
  "name": "Device 1",
  "manufacturer": "Apple Inc.",
  "vendor": null,
  "confidence": 75,
  "ssids": [],
  "is_stationary": false,
  "movement_confidence": 78.5,
  "movement_status": "moving",
  "estimated_location": {
    "lat": 52.4081,
    "lon": 16.9285
  },
  "total_distance_meters": 1523.42,
  "avg_speed_mps": 0.07,
  "avg_speed_kmh": 0.25,
  "max_speed_mps": 1.23,
  "max_speed_kmh": 4.43,
  "observation_duration_seconds": 22033,
  "observation_duration_str": "6h 7m",
  "area_covered_sq_meters": 45231.24,
  "location_clusters": [
    {
      "center_lat": 52.4064,
      "center_lon": 16.9252,
      "sighting_count": 15,
      "avg_rssi": -62.3,
      "first_seen": 1771356932,
      "first_seen_str": "2026-02-17T08:15:32",
      "last_seen": 1771362312,
      "last_seen_str": "2026-02-17T09:45:12",
      "duration_seconds": 5380
    }
  ],
  "movement_segments": [
    {
      "from_lat": 52.4064,
      "from_lon": 16.9252,
      "to_lat": 52.4081,
      "to_lon": 16.9285,
      "start_time": 1771362312,
      "end_time": 1771365000,
      "distance_meters": 312.5,
      "speed_mps": 0.12,
      "speed_kmh": 0.43
    }
  ],
  "path_points": [
    {
      "lat": 52.4064,
      "lon": 16.9252,
      "timestamp": 1771356932,
      "timestamp_str": "2026-02-17T08:15:32",
      "time_display": "08:15:32",
      "rssi": -58,
      "source": "bt",
      "ssid": null,
      "name": "Device 1"
    }
  ]
}
```

## Algorithm

### Location Clustering

Sightings are grouped into clusters using distance-based clustering:

1. **Cluster radius**: 30 meters (configurable via `CLUSTER_RADIUS_METERS`)
2. **Center calculation**: Weighted average of coordinates, with RSSI as weight (stronger signal = more accurate position)
3. **Ordering**: Clusters are sorted chronologically by first sighting time

### Movement Detection

The module determines if a device is stationary or moving based on:

| Metric | Stationary Threshold |
|--------|---------------------|
| Total Distance | < 100 meters |
| Area Covered | < 2500 sq meters |
| Average Speed | < 0.3 m/s |

**Movement Confidence** indicates how certain the classification is:
- High confidence (>80%): Clear stationary or moving pattern
- Medium confidence (50-80%): Some ambiguity
- Low confidence (<50%): Borderline case

### Distance Calculation

Uses the **Haversine formula** for accurate Earth-surface distance:

```python
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000  # Earth's radius in meters
    # ... spherical trigonometry calculation
    return distance_in_meters
```

## Web Interface

The triangulation page (`/triangulate`) provides:

### Left Sidebar
- **Search**: Enter MAC address to analyze
- **Device Information**: MAC, type, name, manufacturer/vendor
- **Movement Analysis**: Status badge (STATIONARY/MOVING), confidence meter
- **Statistics**: Sightings count, distance, area, speed
- **SSIDs**: Known WiFi networks (for WiFi devices)

### Main Content
- **Map**: Interactive visualization with:
  - Green marker: First sighting
  - Red marker: Last sighting  
  - Blue dashed line: Movement path
  - Orange circles: Location clusters
- **Location Clusters**: Detailed list with coordinates
- **Timeline**: Chronological sighting list

### Offline Support

The web interface works fully offline:
- All JavaScript libraries bundled locally (Leaflet, Font Awesome)
- Grid pattern background shown when map tiles unavailable
- "Offline Mode" notice displayed automatically

## Integration with Main App

### Button in Device Tooltip

When clicking on a WiFi or BT device row in the main dashboard, the tooltip shows an **"Analyze Location"** button that opens the triangulation page in a new tab.

### Direct URL Access

Navigate directly to:
```
/triangulate?mac=AA:BB:CC:DD:EE:FF
```

## Configuration

Constants in `triangulation.py`:

```python
class DeviceTriangulator:
    CLUSTER_RADIUS_METERS = 30   # Group sightings within this distance
    MIN_MOVEMENT_DISTANCE = 20   # Minimum distance to consider movement
    MIN_MOVEMENT_SPEED = 0.3     # Minimum speed (m/s) to consider moving
    STATIONARY_MAX_AREA = 2500   # Max area (sq m) for stationary
```

## Use Cases

### Search and Rescue

1. **Locate a missing person's phone**: Analyze sightings to find likely location
2. **Track movement patterns**: Determine if person was moving or stationary
3. **Reconstruct path**: Visualize movement timeline on map

### Field Analysis

1. **Identify base camps**: Stationary devices indicate gathering points
2. **Traffic flow**: Moving devices show common routes
3. **Time-based patterns**: When/where devices were detected

## Troubleshooting

### No data found
- Verify MAC address format (AA:BB:CC:DD:EE:FF)
- Check if device exists in database
- MAC search is case-insensitive

### No location data
- Sightings without GPS coordinates cannot be mapped
- Check if GPS fix was available during scanning

### Inaccurate movement detection
- Few sightings may lead to low confidence
- GPS accuracy affects clustering
- Adjust `CLUSTER_RADIUS_METERS` for your environment

## Files

| File | Description |
|------|-------------|
| `triangulation.py` | Core analysis module (CLI + library) |
| `web_ui/triangulation.html` | Web interface page |
| `web_ui/app.py` | API endpoint (`/api/triangulate/{mac}`) |
