# Device Triangulation Module (v2)

The triangulation module analyzes all sightings for a specific device (identified by MAC address) to determine its location, movement patterns, travel direction, and predicted current position. It works with both Bluetooth and WiFi devices.

## What's New in v2

| # | Improvement | Description |
|---|------------|-------------|
| 1 | **GPS HDOP Weighting** | Sightings with better GPS accuracy (lower HDOP) carry more weight in cluster center calculations |
| 2 | **Per-device tx_power** | Uses actual BLE transmit power from each sighting for RSSI→distance estimation instead of a fixed default |
| 3 | **Temporal Clustering** | Same-location sightings separated by >30 minutes are split into separate clusters, revealing "returned to location" patterns |
| 4 | **Iterative Centroid Expansion** | Clustering now iteratively re-computes the centroid and absorbs nearby unassigned points until stable — fixes chain-proximity issues |
| 5 | **Movement-Aware Location** | For moving devices, the estimated location is the **last known** cluster (most relevant for SAR), not the biggest |
| 6 | **Heading / Direction** | Compass bearing is calculated for each movement segment; last known heading is available for search teams |
| 7 | **Predicted Location** | Extrapolates from last known position + heading + speed to estimate **where the device is NOW** (with uncertainty radius) |
| 8 | **Altitude Analysis** | Fetches and reports altitude min/max/delta from GPS data |
| 9 | **Outlier Filtering** | Flags GPS sightings that are statistical outliers (>3σ MAD from median), preventing phantom movements |
| 10 | **Convex Hull Area** | Area calculation uses a true convex hull (Andrew's algorithm + Shoelace formula) instead of a bounding box |

## Features

- **Location Clustering**: Groups nearby sightings into spatio-temporal location clusters
- **Movement Analysis**: Determines if a device is stationary or moving, with confidence score
- **Heading Estimation**: Compass bearing between consecutive clusters
- **Location Prediction**: Extrapolated "where are they now?" for moving devices
- **Altitude Tracking**: Elevation min/max/delta analysis
- **Outlier Detection**: Flags rogue GPS readings using median absolute deviation
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

## Algorithm

### Analysis Pipeline

```
1. Fetch Sightings  ──→  BT + WiFi (with HDOP, tx_power, altitude)
         │
2. Outlier Filtering ──→  Flag GPS readings >3σ from median
         │
3. Cluster Locations ──→  Spatio-temporal grouping + iterative centroid
         │
4. Analyze Movement  ──→  Distance, speed, heading, convex-hull area
         │
5. Estimate Location ──→  Movement-aware: last-known vs. strongest cluster
         │
6. Predict Location  ──→  Extrapolate from heading + speed (moving only)
         │
7. Altitude Stats    ──→  Min / max / delta elevation
```

### Outlier Filtering

Before clustering, sightings are checked for GPS outliers using **Median Absolute Deviation (MAD)**:

1. Compute the median latitude and longitude across all sightings
2. Compute each sighting's distance from this median point
3. Calculate MAD of these distances, scaled to approximate σ (× 1.4826)
4. Flag sightings where distance > `OUTLIER_DISTANCE_SIGMA × σ` (default: 3.0)

Flagged sightings are **excluded from clustering and path visualization** but remain in the raw sighting count. This prevents phantom movements caused by a single rogue GPS fix.

### Location Clustering

Sightings are grouped into clusters using distance-based clustering with **temporal awareness**:

1. **Cluster radius**: 30 meters (configurable via `CLUSTER_RADIUS_METERS`)
2. **Temporal splitting**: If sightings at the same location are separated by more than `CLUSTER_TIME_GAP_SECONDS` (default: 1800 = 30 min), they form separate clusters. This reveals patterns like "returned to base camp."
3. **Iterative centroid expansion**: After initial assignment, the centroid is recalculated and unassigned nearby points are re-checked. This repeats until no new points are absorbed (up to `CLUSTER_MAX_ITERATIONS`).
4. **Weighted center calculation**: The cluster center is a weighted average combining:
   - **RSSI weight**: `max(1, 100 + rssi)` — stronger signal = more positional accuracy
   - **HDOP weight**: `1 / hdop` — lower HDOP = better GPS fix = more weight
   - **tx_power distance**: `1 / estimated_distance` — closer device = more accurate position

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

### Heading Estimation

For each movement segment between consecutive clusters, the **initial compass bearing** is calculated using the spherical law formula:

```
bearing = atan2(
    sin(Δλ) × cos(φ₂),
    cos(φ₁) × sin(φ₂) - sin(φ₁) × cos(φ₂) × cos(Δλ)
)
```

Headings are reported as:
- Degrees: 0° = North, 90° = East, 180° = South, 270° = West
- Cardinal: N, NNE, NE, ENE, E, ESE, SE, SSE, S, SSW, SW, WSW, W, WNW, NW, NNW

The **last known heading** from the final movement segment is prominently displayed in the output.

### Predicted Location

For **moving devices only**, the module extrapolates a predicted current position:

1. Uses the **last known location**, **last known heading**, and **last segment speed** (or average speed as fallback)
2. Computes elapsed time since last sighting
3. Projects the position forward: `destination = last_known + speed × elapsed @ heading`
4. Calculates an uncertainty radius: `uncertainty = distance × PREDICTION_UNCERTAINTY_RATE` (default: 2×), minimum 50 m
5. **Limits**: No prediction if device is stationary, speed < 0.05 m/s, or elapsed > `PREDICTION_MAX_ELAPSED` (2 hours)

This answers the critical SAR question: **"Where might they be NOW?"**

### Altitude Analysis

GPS altitude data is collected when available and used to compute:

| Metric | Description |
|--------|-------------|
| `altitude_min` | Lowest recorded elevation (meters) |
| `altitude_max` | Highest recorded elevation (meters) |
| `altitude_delta` | Total elevation change (max - min) |
| `sightings_with_altitude` | Number of sightings that had altitude data |

Cluster-level average altitude is also computed and shown per cluster.

### Area Calculation

Area covered is computed using a **convex hull** (Andrew's monotone-chain algorithm) with the **Shoelace formula** for polygon area, after converting lat/lon to local meters. Falls back to bounding-box for fewer than 3 points.

### Distance Calculation

Uses the **Haversine formula** for accurate Earth-surface distance:

```python
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000  # Earth's radius in meters
    # ... spherical trigonometry calculation
    return distance_in_meters
```

### RSSI → Distance Estimation

Uses a **log-distance path-loss model** with per-sighting `tx_power` when available:

```python
def estimate_distance_from_rssi(rssi, tx_power=-59):
    n = 2.5  # path-loss exponent (outdoor)
    ratio = (tx_power - rssi) / (10 * n)
    return 10 ** ratio
```

## Output

### Text Output (CLI)

```
============================================================
DEVICE TRIANGULATION ANALYSIS (v2)
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
  Outliers Filtered:     2
  First Seen:            2026-02-17 08:15:32
  Last Seen:             2026-02-17 14:22:45
  Observation Duration:  6h 7m

MOVEMENT ANALYSIS
----------------------------------------
  Status:                MOVING
  Confidence:            78.5%
  Total Distance:        1523.4 m
  Area Covered:          38420.7 sq m
  Average Speed:         0.07 m/s (0.25 km/h)
  Maximum Speed:         1.23 m/s (4.43 km/h)
  Last Heading:          47.3° (NE)

ALTITUDE ANALYSIS
----------------------------------------
  Sightings with Alt:    35
  Altitude Min:          82.3 m
  Altitude Max:          127.8 m
  Altitude Delta:        45.5 m

LOCATION CLUSTERS
----------------------------------------
  Cluster #1:
    Center:     (52.406400, 16.925200)
    Sightings:  12
    Avg RSSI:   -62.3 dBm
    Avg HDOP:   1.20
    Avg Alt:    89.5 m
    First Seen: 08:15:32
    Last Seen:  09:45:12

  Cluster #2:
    Center:     (52.408100, 16.928500)
    Sightings:  18
    Avg RSSI:   -55.1 dBm
    Avg HDOP:   0.90
    Avg Alt:    115.2 m
    First Seen: 11:30:00
    Last Seen:  14:22:45

MOVEMENT SEGMENTS
----------------------------------------
  #1: 420 m @ 0.4 km/h  heading 47° (NE)

ESTIMATED PRIMARY LOCATION
----------------------------------------
  Latitude:  52.408100
  Longitude: 16.928500
  https://www.google.com/maps?q=52.4081,16.9285

PREDICTED CURRENT LOCATION
----------------------------------------
  Based on:  2h 15m since last sighting
  Latitude:  52.410300
  Longitude: 16.931200
  Uncertainty: ±1240 m radius
  https://www.google.com/maps?q=52.4103,16.9312

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
  "is_stationary": false,
  "movement_confidence": 78.5,
  "movement_status": "moving",
  "estimated_location": { "lat": 52.4081, "lon": 16.9285 },
  "last_known_location": { "lat": 52.4081, "lon": 16.9285 },
  "predicted_location": {
    "lat": 52.4103,
    "lon": 16.9312,
    "uncertainty_meters": 1240.0,
    "elapsed_seconds": 8100,
    "elapsed_str": "2h 15m"
  },
  "last_known_heading": 47.3,
  "last_known_heading_cardinal": "NE",
  "total_distance_meters": 1523.42,
  "avg_speed_mps": 0.07,
  "avg_speed_kmh": 0.25,
  "max_speed_mps": 1.23,
  "max_speed_kmh": 4.43,
  "observation_duration_seconds": 22033,
  "observation_duration_str": "6h 7m",
  "area_covered_sq_meters": 38420.71,
  "altitude_min": 82.3,
  "altitude_max": 127.8,
  "altitude_delta": 45.5,
  "sightings_with_altitude": 35,
  "outliers_filtered": 2,
  "location_clusters": [
    {
      "center_lat": 52.4064,
      "center_lon": 16.9252,
      "sighting_count": 12,
      "avg_rssi": -62.3,
      "avg_hdop": 1.2,
      "avg_alt": 89.5,
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
      "distance_meters": 420.0,
      "speed_mps": 0.16,
      "speed_kmh": 0.57,
      "heading_degrees": 47.3,
      "heading_cardinal": "NE"
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
      "name": "Device 1",
      "alt": 85.2,
      "hdop": 1.1
    }
  ]
}
```

## Web Interface

The triangulation page (`/triangulate`) provides:

### Left Sidebar
- **Search**: Enter MAC address to analyze
- **Device Information**: MAC, type, name, manufacturer/vendor
- **Movement Analysis**: Status badge (STATIONARY/MOVING), confidence meter, heading
- **Statistics**: Sightings count, distance, area, speed, altitude
- **Prediction**: Where the device might be now (with uncertainty)
- **SSIDs**: Known WiFi networks (for WiFi devices)

### Main Content
- **Map**: Interactive visualization with:
  - Green marker: First sighting
  - Red marker: Last sighting
  - Blue dashed line: Movement path
  - Orange circles: Location clusters
- **Location Clusters**: Detailed list with coordinates, HDOP, altitude
- **Timeline**: Chronological sighting list

### Offline Support

The web interface works fully offline:
- All JavaScript libraries bundled locally (Leaflet, Font Awesome)
- Grid pattern background shown when map tiles unavailable
- "Offline Mode" notice displayed automatically

## Configuration

Constants in `triangulation.py`:

```python
class DeviceTriangulator:
    # Clustering
    CLUSTER_RADIUS_METERS = 30        # Group sightings within this distance
    CLUSTER_TIME_GAP_SECONDS = 1800   # Split cluster if gap > 30 minutes
    CLUSTER_MAX_ITERATIONS = 10       # Max centroid-expansion iterations
    MIN_MOVEMENT_DISTANCE = 20        # Minimum distance to consider movement
    MIN_MOVEMENT_SPEED = 0.3          # Minimum speed (m/s) to consider moving
    STATIONARY_MAX_AREA = 2500        # Max area (sq m) for stationary

    # Outlier detection
    OUTLIER_DISTANCE_SIGMA = 3.0      # Flag sightings >3σ from median

    # Prediction
    PREDICTION_MAX_ELAPSED = 7200     # Don't predict beyond 2 hours
    PREDICTION_UNCERTAINTY_RATE = 2.0 # Uncertainty grows at 2× speed
```

## Use Cases

### Search and Rescue

1. **Locate a missing person's phone**: Analyze sightings to find likely location, weighted by GPS quality and signal strength
2. **Track movement patterns**: Determine if person was moving or stationary, with temporal cluster splitting to reveal revisited locations
3. **Get last known heading**: Know which direction the person was traveling when last detected
4. **Predict current location**: Extrapolate where they might be NOW based on speed + heading, with uncertainty radius for search planning
5. **Elevation analysis**: Detect altitude changes indicating terrain traversal (hills, valleys, building floors)

### Field Analysis

1. **Identify base camps**: Stationary devices indicate gathering points
2. **Traffic flow**: Moving devices show common routes with compass bearings
3. **Time-based patterns**: When/where devices were detected, including revisits
4. **GPS quality assessment**: HDOP values indicate reliability of each position fix

## Database Fields Used

The triangulation module is **read-only** — it does not modify the database or require schema changes.

### From `sightings` table (BT)

| Column | Used For |
|--------|----------|
| `ts_unix` | Timestamp ordering, temporal clustering |
| `lat`, `lon` | Spatial clustering, movement path |
| `rssi` | Cluster center weighting |
| `local_name` | Display in path points |
| `scanner_name` | Source identification |
| `gps_hdop` | **v2**: GPS quality weighting |
| `tx_power` | **v2**: RSSI→distance estimation |
| `alt` | **v2**: Altitude analysis |

### From `wifi_associations` table (WiFi)

| Column | Used For |
|--------|----------|
| `ts_unix` | Timestamp ordering |
| `lat`, `lon` | Spatial clustering |
| `rssi` | Cluster center weighting |
| `ssid` | Display in path points |
| `scanner_name` | Source identification |
| `alt` | **v2**: Altitude analysis (if column exists) |

## Troubleshooting

### No data found
- Verify MAC address format (AA:BB:CC:DD:EE:FF)
- Check if device exists in database
- MAC search is case-insensitive

### No location data
- Sightings without GPS coordinates cannot be mapped
- Check if GPS fix was available during scanning

### Outliers removed
- If valid sightings are flagged, increase `OUTLIER_DISTANCE_SIGMA` (default: 3.0)
- Check GPS antenna placement — poor fixes have high HDOP

### No predicted location
- Only computed for **moving** devices
- Not shown if last sighting is > 2 hours old (`PREDICTION_MAX_ELAPSED`)
- Not shown if speed is very low (< 0.05 m/s)

### Inaccurate movement detection
- Few sightings may lead to low confidence
- GPS accuracy affects clustering — check HDOP values
- Adjust `CLUSTER_RADIUS_METERS` for your environment
- Adjust `CLUSTER_TIME_GAP_SECONDS` if visits are being incorrectly merged/split

## Files

| File | Description |
|------|-------------|
| `triangulation.py` | Core analysis module (CLI + library) |
| `web_ui/triangulation.html` | Web interface page |
| `web_ui/app.py` | API endpoint (`/api/triangulate/{mac}`) |
