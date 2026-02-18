# Confidence Analyzer Module

## Overview

The Confidence Analyzer is a standalone module that evaluates device sighting patterns to estimate how likely each detected device belongs to a missing person versus SAR (Search and Rescue) team equipment.

This helps SAR teams quickly identify devices of interest by filtering out their own equipment, vehicles, drones, and HQ devices from the scan results.

## Key Features

- **Rule-based scoring** with 8 analysis factors
- **GPS clustering** - identifies devices near HQ vs in the field
- **Device whitelist** - automatically exclude known SAR team devices
- **Multi-session detection** - recognizes devices appearing across separate search sessions
- **Web UI integration** - preview and apply analysis from the dashboard
- **CLI interface** - scriptable analysis for automation

## Confidence Scale

| Range | Interpretation |
|-------|----------------|
| 0-30 | Likely SAR team equipment |
| 31-69 | Uncertain / needs investigation |
| 70-100 | Possible missing person's device |

## Usage

### Command Line Interface

```bash
# Run analysis and update database
python confidence_analyzer.py

# Preview analysis without modifying database
python confidence_analyzer.py --dry-run

# Verbose output showing all device analyses
python confidence_analyzer.py -v

# Skip confirmation prompt
python confidence_analyzer.py --yes

# Full preview with details
python confidence_analyzer.py --dry-run -v
```

### Web UI

1. Open the web interface at `http://<scanner-ip>:8000`
2. In the left sidebar, find the "Confidence Analysis" section
3. Click the green **"Analyze Confidence"** button
4. Review the preview showing:
   - Session duration
   - Total devices analyzed
   - High/low confidence counts
   - Top device changes
5. Click **"Apply Changes"** to update the database

## Algorithm Details

The analyzer starts with a baseline confidence of **50** (neutral) and adjusts based on **8 factors**:

### Factor 1: Presence Ratio

How long the device was present relative to the total session duration.

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| Present >80% of session | -30 | Device always there = SAR team |
| Present 50-80% of session | -15 | Frequently present |
| Present <20% of session | +15 | Brief appearance, more interesting |

### Factor 2: Session Boundary Presence

Whether the device was detected at the start and/or end of the scanning session.

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| Strong RSSI at BOTH start AND end | -25 | HQ equipment stays in place |
| Present at both boundaries (any RSSI) | -10 | Likely team equipment |
| Only mid-session appearance | +25 | Appeared during search, then gone |
| Present at start, disappeared | +10 | Could be person who left area |
| Not present at start, appeared later | +10 | Could be person entering area |

**Note:** "Strong RSSI" is defined as > -60 dBm

### Factor 3: Sighting Frequency

How often the device was detected relative to expected scan cycles.

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| Very high sighting rate (>70% of cycles) | -15 | Constantly present = SAR vehicle |
| Low sighting count (≤3 total) | +10 | Fleeting appearance |

### Factor 4: Signal Strength Profile

Average signal strength throughout the session.

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| Very weak average (<-80 dBm) | +5 | Distant device, possibly target |
| Very strong average (>-50 dBm) | -5 | Close/HQ equipment |

### Factor 5: GPS/HQ Proximity Ratio (NEW)

What percentage of sightings occurred near the HQ/base location.

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| >90% of sightings near HQ | -20 | Base equipment, never moves |
| <20% of sightings near HQ | +15 | Field device, rarely at base |

**Note:** "Near HQ" is defined by `HQ_RADIUS_METERS` (default: 100m)

### Factor 6: Average Distance from HQ (NEW)

Mean distance (in meters) from HQ across all sightings with GPS data.

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| Average distance >500m | +10 | Consistently far from base |
| Average distance <50m | -10 | Always at base location |

### Factor 7: Multi-Session Detection (NEW)

Whether the device was seen across multiple separate sessions (gaps > 2 hours).

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| Seen in 3+ sessions | -15 | Persistent presence = SAR team |
| Seen in 2 sessions | -5 | Recurring presence |

### Factor 8: Device Whitelist (NEW)

Devices in the whitelist file are automatically assigned confidence 0.

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| MAC in whitelist | = 0 | Known SAR team equipment |

## Session Boundaries

The analyzer defines "early" and "late" boundaries as the first and last **10%** of the session duration:

```
|----10%----|----------------80%-----------------|----10%----|
  EARLY                    MID                        LATE
```

## GPS Distance Calculation

Device distances from HQ are calculated using the **Haversine formula**, which accounts for Earth's curvature:

```python
distance = 2 * R * arcsin(sqrt(
    sin²((lat2-lat1)/2) + cos(lat1) * cos(lat2) * sin²((lon2-lon1)/2)
))
```

Where R = 6,371,000 meters (Earth's radius).

This provides accurate distances even for remote locations where GPS coordinates may span significant geographic areas.

## Multi-Session Detection

Sessions are automatically detected based on gaps in sighting timestamps:

```
|--Session 1--|    2+ hour gap    |--Session 2--|    2+ hour gap    |--Session 3--|
```

A gap of `SESSION_GAP_SECONDS` (default: 7200 = 2 hours) or more indicates a new session. Devices seen across multiple sessions are more likely to be SAR equipment that returns to base between search operations.

## Examples

### Example 1: SAR Team Radio at HQ (Confidence: 0)

- Present throughout entire session (presence ratio 100%)
- Strong signal at both start and end
- Always near HQ location
- High sighting count

```
Factors:
- High presence ratio (100%) → -30
- Strong RSSI at start (-45) AND end (-42) → -25
- Very high sighting rate (85%) → -15
- Very strong average signal (-44 dBm) → -5
- Seen mostly near HQ (95%) → -20
- Avg distance from HQ: 15m → -10
= Final: 50 - 30 - 25 - 15 - 5 - 20 - 10 = 0 (capped at 0)
```

### Example 2: Passing Hiker's Phone (Confidence: 100)

- Appeared only mid-session
- Brief presence (~15 minutes in 2-hour session)
- Low sighting count
- Only seen far from HQ

```
Factors:
- Low presence ratio (12%) → +15
- Only mid-session appearance → +25
- Low sighting count (4) → +10
- Rarely seen near HQ (0%) → +15
- Avg distance from HQ: 850m → +10
= Final: 50 + 15 + 25 + 10 + 15 + 10 = 100 (capped at 100)
```

### Example 3: HQ Computer (Confidence: 0)

- Present at boundaries with strong signal
- High presence ratio
- Stationary at HQ throughout

```
Factors:
- High presence ratio (100%) → -30
- Strong RSSI at start AND end → -25
- Seen mostly near HQ (100%) → -20
- Avg distance from HQ: 5m → -10
= Final: 50 - 30 - 25 - 20 - 10 = 0 (capped)
```

### Example 4: Field Searcher's Phone (Confidence: ~35)

- Whitelisted device

```
Factors:
- Whitelisted device (SAR team equipment) → 0
= Final: 0
```

### Example 5: Device Seen Across Multiple Days (Confidence: ~25)

- Seen in morning and evening sessions
- Present at HQ during both
- Recurring pattern suggests team equipment

```
Factors:
- Medium presence ratio (60%) → -15
- Present at session boundaries → -10
- Seen in 2 sessions → -5
- Seen mostly near HQ (80%) → (no adjustment, between thresholds)
= Final: 50 - 15 - 10 - 5 = 20
```

## Data Requirements

The analyzer requires:

- **BT Devices**: `devices` table with `addr`, `first_seen`, `last_seen`, `confidence`
- **BT Sightings**: `sightings` table with `addr`, `ts_unix`, `rssi`, `lat`, `lon`
- **WiFi Devices**: `wifi_devices` table with `mac`, `first_seen`, `last_seen`, `confidence`
- **WiFi Associations**: `wifi_associations` table with `mac`, `ts_unix`, `rssi`, `lat`, `lon`

**Note:** GPS coordinates (`lat`, `lon`) are optional but enable GPS-based analysis factors.

## API Endpoints

### Preview Analysis

```
GET /api/analyze/confidence/preview
```

Returns analysis preview without modifying database.

**Response:**
```json
{
  "session": {
    "start": "2026-02-17T10:00:00",
    "end": "2026-02-17T14:30:00",
    "duration_seconds": 16200,
    "duration_human": "270m 0s"
  },
  "devices": {
    "bt_total": 45,
    "wifi_total": 23,
    "high_confidence": 5,
    "low_confidence": 38,
    "whitelisted": 3,
    "with_gps_data": 42,
    "multi_session": 8
  },
  "config": {
    "hq_location": [52.2297, 21.0122],
    "hq_radius_meters": 100,
    "session_gap_seconds": 7200,
    "whitelist_count": 5
  },
  "devices_detail": [...],
  "high_confidence_devices": [...],
  "preview": true
}
```

### Apply Analysis

```
POST /api/analyze/confidence
```

Runs analysis and updates database.

**Response:**
```json
{
  "session": {...},
  "devices": {...},
  "config": {...},
  "updates": {
    "bt_updated": 45,
    "wifi_updated": 23
  },
  "applied": true
}
```

## Configuration

### settings.py Options

```python
# HQ/base location for GPS clustering analysis
# Set to your staging area coordinates, or leave as None for auto-detect
HQ_LATITUDE = None           # e.g., 52.2297
HQ_LONGITUDE = None          # e.g., 21.0122
HQ_RADIUS_METERS = 100       # Devices within this radius are "near HQ"

# Path to device whitelist file
DEVICE_WHITELIST_FILE = "device_whitelist.txt"

# Gap threshold for multi-session detection (seconds)
SESSION_GAP_SECONDS = 7200   # 2 hours = new session boundary
```

### Device Whitelist

Create a `device_whitelist.txt` file with known SAR team device MAC addresses:

```text
# SAR Team Equipment - automatically get confidence = 0
# One MAC per line, comments start with #

# Team Leader's phone
AA:BB:CC:DD:EE:01

# SAR vehicle tracker
11-22-33-44-55-66

# Drone controller
AA:BB:CC:11:22:33
```

MAC addresses are normalized (case-insensitive, colons or dashes accepted).

### Algorithm Thresholds

The analyzer thresholds can be adjusted by modifying the class constants in `confidence_analyzer.py`:

```python
class ConfidenceAnalyzer:
    # Session boundary analysis
    BOUNDARY_PERCENT = 0.10       # First/last 10% of session
    STRONG_RSSI_THRESHOLD = -60   # dBm threshold for "strong" signal
    
    # Presence analysis
    HIGH_PRESENCE_RATIO = 0.80    # >80% = high presence
    MEDIUM_PRESENCE_RATIO = 0.50  # >50% = medium presence
    HIGH_SIGHTING_RATE = 0.70     # >70% of expected cycles
    
    # GPS clustering thresholds
    HQ_RATIO_HIGH = 0.90          # >90% near HQ = base equipment
    HQ_RATIO_LOW = 0.20           # <20% near HQ = field device
```

### HQ Location Auto-Detection

If `HQ_LATITUDE` and `HQ_LONGITUDE` are not set (None), the analyzer automatically detects HQ location from the first GPS sighting in the database. This assumes the scanner starts at the base/staging area.

## Limitations

1. **Rule-Based Only**: Currently uses heuristic rules. Future versions may incorporate ML models trained on labeled SAR data.

2. **Device Name Ignorance**: Does not factor in device names or manufacturer data, which could provide additional context.

3. **Single Scanner**: Does not cross-reference data from multiple scanners to improve accuracy.

4. **No Movement Analysis**: Does not calculate velocity or trajectory patterns from GPS data.

## Future Enhancements

### High Priority
- [ ] Machine learning model trained on historical SAR session data
- [ ] Cross-scanner correlation (multi-device consistency analysis)
- [ ] Velocity estimation from GPS path analysis
- [ ] Time-of-day patterns (devices at unusual hours)

### Medium Priority
- [ ] Device name/manufacturer analysis (filter known SAR equipment brands)
- [ ] Behavior fingerprinting (probe patterns, SSID preferences)
- [ ] Signal trajectory visualization on map
- [ ] Alert system for high-confidence devices

### Lower Priority
- [ ] Integration with external missing person device databases
- [ ] Historical trend analysis dashboard
- [ ] Automated report generation
