# Confidence Analyzer Module

## Overview

The Confidence Analyzer is a standalone module that evaluates device sighting patterns to estimate how likely each detected device belongs to a missing person versus SAR (Search and Rescue) team equipment.

This helps SAR teams quickly identify devices of interest by filtering out their own equipment, vehicles, drones, and HQ devices from the scan results.

## Key Features

- **Rule-based scoring** with 18 analysis factors (v2)
- **GPS clustering** - identifies devices near HQ vs in the field
- **GPS spatial spread** - detects moving vs stationary devices
- **RSSI trend analysis** - detects pass-by patterns (rise-then-fall signal)
- **WiFi SSID probing** - personal phones probe for remembered networks
- **WiFi packet type** - distinguishes clients (ProbeRequest) from APs (Beacon)
- **MAC randomization detection** - randomized MACs indicate modern personal devices
- **Device name/manufacturer classification** - identifies personal vs SAR equipment
- **Sighting burstiness** - irregular patterns suggest a person passing through
- **Cross-scanner consistency** - devices seen by many scanners are likely SAR equipment
- **Active presence ratio** - time-bucketed presence for accurate occupancy
- **Signal convergence** - boosts confidence when multiple signals agree
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

The analyzer starts with a baseline confidence of **50** (neutral) and adjusts based on **18 factors**:

### Factor 1: Presence Ratio

How long the device was present relative to the total session duration (span-based).

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

**Note:** "Strong RSSI" is defined as > -60 dBm

### Factor 3: Mid-Session Appearance

Whether the device appeared only during the middle of the session.

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| Only mid-session appearance | +25 | Appeared during search, then gone |
| Present at start, disappeared | +10 | Could be person who left area |
| Not present at start, appeared later | +10 | Could be person entering area |

### Factor 4: Sighting Frequency

How often the device was detected relative to expected scan cycles.

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| Very high sighting rate (>70% of cycles) | -15 | Constantly present = SAR vehicle |
| Low sighting count (≤3 total) | +10 | Fleeting appearance |

### Factor 5: Signal Strength Profile

Average signal strength throughout the session.

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| Very weak average (<-80 dBm) | +5 | Distant device, possibly target |
| Very strong average (>-50 dBm) | -5 | Close/HQ equipment |

### Factor 6: GPS/HQ Proximity Ratio

What percentage of sightings occurred near the HQ/base location.

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| >90% of sightings near HQ | -20 | Base equipment, never moves |
| <20% of sightings near HQ | +15 | Field device, rarely at base |

**Note:** "Near HQ" is defined by `HQ_RADIUS_METERS` (default: 100m)

### Factor 7: Average Distance from HQ

Mean distance (in meters) from HQ across all sightings with GPS data.

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| Average distance >500m | +10 | Consistently far from base |
| Average distance <50m | -10 | Always at base location |

### Factor 8: Multi-Session Detection

Whether the device was seen across multiple separate sessions (gaps > 2 hours).

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| Seen in 3+ sessions | -15 | Persistent presence = SAR team |
| Seen in 2 sessions | -5 | Recurring presence |

### Factor 9: RSSI Trend / Variance (NEW v2)

Analyzes signal strength variation and patterns over time. A "rise-then-fall" pattern is classic for someone walking past the scanner.

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| Rise-then-fall peak detected | +15 | Device passed by scanner |
| High RSSI variance (σ > 10 dBm) | +8 | Moving/changing distance |
| Low RSSI variance (σ < 3 dBm, 5+ sightings) | -8 | Stationary device |

**How peak detection works:** The sighting sequence is split into quarters. If the middle portion's average RSSI is ≥3 dBm stronger than both the first and last quarters, a "pass-by" peak is detected.

### Factor 10: WiFi SSID Probing (NEW v2, WiFi only)

Personal phones probe for multiple remembered WiFi networks. SAR infrastructure typically probes for zero or one.

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| Probes 3+ unique SSIDs | +12 | Personal device with network history |
| Probes 1-2 SSIDs | +5 | Some network memory |

**Note:** Hidden SSIDs and empty SSIDs are excluded from the count.

### Factor 11: MAC Randomization (NEW v2)

Modern smartphones (iOS 14+, Android 10+) use randomized (locally-administered) MAC addresses for privacy. A randomized MAC strongly indicates a personal device.

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| Randomized MAC (locally-administered bit set) | +10 | Modern smartphone/tablet |

**Detection:** Checks bit 1 of the first MAC octet (0x02 mask). If set, the address is locally-administered (randomized).

### Factor 12: Device Name/Manufacturer Classification (NEW v2)

Checks BLE advertised name and manufacturer against keyword lists to identify personal devices vs SAR equipment.

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| Personal device keyword match | +12 | iPhone, Galaxy, AirPods, etc. |
| SAR equipment keyword match | -15 | Garmin, Kenwood, DJI, etc. |

**Personal keywords:** iphone, ipad, galaxy, samsung, pixel, airpods, fitbit, beats, jbl, tile, airtag, etc.

**SAR/infrastructure keywords:** garmin, kenwood, motorola solutions, baofeng, dji, drone, ubiquiti, cisco, raspberry, esp32, etc.

### Factor 13: Sighting Burstiness (NEW v2)

Coefficient of variation (CoV) of inter-sighting time intervals. Bursty/irregular patterns suggest a person passing through; regular/periodic patterns suggest always-on SAR equipment.

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| High CoV (> 1.5) | +8 | Irregular/bursty = passing through |
| Low CoV (< 0.3) | -8 | Very regular/periodic = static equipment |

**CoV formula:** standard deviation of intervals / mean of intervals

### Factor 14: WiFi Packet Type (NEW v2, WiFi only)

Distinguishes between Access Points (Beacon frames) and client devices (Probe Requests).

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| Beacon-only (AP) | -20 | Access point = infrastructure |
| ProbeRequest-only (client) | +5 | Client device = personal |

### Factor 15: GPS Spatial Spread (NEW v2)

Mean distance of all sighting locations from their centroid. Large spread indicates the device is moving through the area.

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| Spread > 200m | +10 | Moving device |
| Spread < 20m (5+ sightings) | -5 | Stationary device |

### Factor 16: Cross-Scanner Consistency (NEW v2)

How many distinct scanners detected this device. Devices seen by many scanners are likely ubiquitous SAR team equipment.

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| Seen by 3+ scanners | -8 | Ubiquitous = SAR equipment |
| Single scanner, ≤5 sightings | +3 | Localized appearance |

### Factor 17: Active Presence Ratio (NEW v2)

Detects discrepancy between time span and actual sighting density. A device with a long time span but few actual sightings appeared sporadically — not continuously.

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| Span ratio > 50% but active ratio < 15% | +10 | Sporadic, not continuous presence |

**Active ratio:** Divides session into 60-second buckets and counts occupied ones.

### Factor 18: Signal Convergence (NEW v2)

Meta-factor that rewards/penalizes when multiple independent factors agree in the same direction.

| Condition | Score Adjustment | Rationale |
|-----------|------------------|-----------|
| 5+ positive factors | +10 | Strong multi-signal agreement |
| 4 positive factors | +5 | Moderate agreement |
| 5+ negative factors | -10 | Strong multi-signal agreement |
| 4 negative factors | -5 | Moderate agreement |

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

## RSSI Trend Analysis

The analyzer fits a linear regression to RSSI values over time and computes signal variance:

```
RSSI (dBm)
   ^
-40│          ╱╲
-50│        ╱    ╲         ← Rise-then-fall = device passed by scanner
-60│      ╱        ╲
-70│    ╱            ╲
-80│──╱                ╲──
   └──────────────────────→ Time
```

The peak detection algorithm splits readings into quarters and checks if the middle portion is significantly stronger than the edges (≥3 dBm delta).

## WiFi SSID Analysis

Personal devices (phones, tablets) typically probe for 3-15 remembered WiFi networks:

```
Phone probes:  "HomeWiFi", "OfficeNet", "CoffeeShopFree", "eduroam"  → 4 SSIDs → +12
SAR radio:     (no probes)                                            → 0 SSIDs → no change
Drone hotspot: Beacon "DJI_Mavic_3"                                   → Beacon  → -20
```

## Examples

### Example 1: SAR Team Radio at HQ (Confidence: 0)

- Present throughout entire session (presence ratio 100%)
- Strong signal at both start and end
- Always near HQ location
- High sighting count, low RSSI variance

```
Factors:
- High presence ratio (100%) → -30
- Strong RSSI at start (-45) AND end (-42) → -25
- Very high sighting rate (85%) → -15
- Very strong average signal (-44 dBm) → -5
- Seen mostly near HQ (95%) → -20
- Avg distance from HQ: 15m → -10
- Low RSSI variance (σ=1.5 dBm) → -8
- Regular sighting pattern (CoV=0.15) → -8
- Tiny GPS spread (8m) → -5
- SAR/infrastructure equipment (Kenwood) → -15
- Strong signal convergence: 9 negative indicators → -10
= Final: 50 - 30 - 25 - 15 - 5 - 20 - 10 - 8 - 8 - 5 - 15 - 10 = 0 (capped)
```

### Example 2: Missing Person's Phone (Confidence: 100)

- Appeared only mid-session
- Brief presence (~15 minutes in 2-hour session)
- Low sighting count, rise-then-fall RSSI
- Randomized MAC, probing for home networks

```
Factors:
- Low presence ratio (12%) → +15
- Only mid-session appearance → +25
- Low sighting count (4) → +10
- Rarely seen near HQ (0%) → +15
- Avg distance from HQ: 850m → +10
- RSSI rise-then-fall pattern → +15
- Probes 4 unique SSIDs → +12
- Randomized MAC → +10
- Personal device (iPhone) → +12
- Bursty sighting pattern (CoV=2.1) → +8
- ProbeRequest-only (client) → +5
- Large GPS spread (320m) → +10
- Single scanner, few sightings → +3
- Strong signal convergence: 13 positive indicators → +10
= Final: 50 + 160 = 100 (capped)
```

### Example 3: Drone Controller (Confidence: 0)

- Beacon device broadcasting SSID
- Present at HQ
- SAR equipment keywords match

```
Factors:
- High presence ratio (90%) → -30
- Strong RSSI at start AND end → -25
- Beacon-only device (AP) → -20
- SAR/infrastructure equipment (DJI / drone) → -15
- Seen mostly near HQ (100%) → -20
- Regular sighting pattern (CoV=0.12) → -8
- Strong signal convergence: 6 negative indicators → -10
= Final: 0 (capped)
```

### Example 4: Whitelisted Field Searcher's Phone (Confidence: 0)

```
Factors:
- Whitelisted device (SAR team equipment) → 0
= Final: 0
```

### Example 5: Suspicious Device - Needs Investigation (Confidence: ~65)

- Device appeared mid-session but hung around
- Medium presence, some RSSI variation
- Not near HQ, but not far either

```
Factors:
- Not present at start, appeared later → +10
- Weak average signal (-82 dBm) → +5
- High RSSI variance (σ=12 dBm) → +8
- Randomized MAC → +10
- Active presence lower than span (10% vs 55%) → +10
- Bursty sighting pattern (CoV=1.8) → +8
= Final: 50 + 10 + 5 + 8 + 10 + 10 + 8 = 101 → capped at 100
```

## Data Requirements

The analyzer requires:

- **BT Devices**: `devices` table with `addr`, `first_seen`, `last_seen`, `confidence`, `name`, `manufacturer`
- **BT Sightings**: `sightings` table with `addr`, `ts_unix`, `rssi`, `lat`, `lon`, `scanner_name`
- **WiFi Devices**: `wifi_devices` table with `mac`, `first_seen`, `last_seen`, `confidence`
- **WiFi Associations**: `wifi_associations` table with `mac`, `ts_unix`, `rssi`, `lat`, `lon`, `ssid`, `packet_type`, `scanner_name`

**Note:** GPS coordinates (`lat`, `lon`) are optional but enable GPS-based analysis factors (6, 7, 15).

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
    "multi_session": 8,
    "randomized_macs": 12,
    "beacon_devices": 4,
    "rssi_peak_detected": 3
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
    
    # RSSI trend thresholds (NEW v2)
    RSSI_HIGH_VARIANCE_THRESHOLD = 10.0  # σ > 10 dBm = moving
    RSSI_LOW_VARIANCE_THRESHOLD = 3.0    # σ < 3 dBm = stationary
    RSSI_PEAK_MIN_DELTA = 3.0            # Min dBm for peak detection
    
    # Burstiness thresholds (NEW v2)
    HIGH_BURSTINESS_COV = 1.5     # CoV > 1.5 = bursty
    LOW_BURSTINESS_COV = 0.3      # CoV < 0.3 = periodic
    
    # GPS spread thresholds (NEW v2)
    HIGH_GPS_SPREAD = 200         # > 200m = moving device
    LOW_GPS_SPREAD = 20           # < 20m = stationary
    
    # Active presence bucket size (NEW v2)
    PRESENCE_BUCKET_SECONDS = 60  # 1-minute buckets
```

### Keyword Lists

Personal device and SAR equipment keywords can be customized directly in `confidence_analyzer.py`:

```python
    PERSONAL_DEVICE_KEYWORDS = [
        'iphone', 'ipad', 'galaxy', 'samsung', 'pixel', 'airpods',
        'fitbit', 'beats', 'jbl', 'tile', 'airtag', ...
    ]
    
    SAR_EQUIPMENT_KEYWORDS = [
        'garmin', 'kenwood', 'motorola solutions', 'baofeng',
        'dji', 'drone', 'ubiquiti', 'cisco', 'raspberry', ...
    ]
```

### HQ Location Auto-Detection

If `HQ_LATITUDE` and `HQ_LONGITUDE` are not set (None), the analyzer automatically detects HQ location from the first GPS sighting in the database. This assumes the scanner starts at the base/staging area.

## Limitations

1. **Rule-Based Only**: Currently uses heuristic rules with configurable thresholds. Future versions may incorporate ML models trained on labeled SAR data.

2. **SSID Content Not Analyzed**: The analyzer counts unique SSIDs but does not classify them (e.g., carrier hotspot names vs home networks). Future versions could use SSID dictionaries.

3. **No Velocity Estimation**: GPS spread detects movement but does not calculate speed or trajectory.

## Future Enhancements

### High Priority
- [ ] Machine learning model trained on historical SAR session data
- [ ] SSID dictionary classification (carrier hotspots, eduroam, home networks)
- [ ] Velocity estimation from GPS path analysis

### Medium Priority
- [ ] Signal trajectory visualization on map
- [ ] Alert system for high-confidence devices
- [ ] Integration with external missing person device databases
- [ ] Behavior fingerprinting (BLE advertisement patterns)

### Lower Priority
- [ ] Historical trend analysis dashboard
- [ ] Automated report generation
- [ ] Custom keyword lists via configuration file (instead of code)

### Completed (v2)
- [x] Device name/manufacturer analysis
- [x] WiFi SSID probing analysis
- [x] WiFi packet type classification (Beacon vs ProbeRequest)
- [x] MAC randomization detection
- [x] RSSI trend and variance analysis
- [x] Sighting burstiness (temporal clustering)
- [x] GPS spatial spread (movement detection)
- [x] Cross-scanner correlation
- [x] Active presence ratio (time-bucketed)
- [x] Signal convergence meta-factor
