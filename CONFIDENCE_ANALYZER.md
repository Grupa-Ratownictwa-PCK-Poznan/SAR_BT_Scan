# Confidence Analyzer Module

## Overview

The Confidence Analyzer is a standalone module that evaluates device sighting patterns to estimate how likely each detected device belongs to a missing person versus SAR (Search and Rescue) team equipment.

This helps SAR teams quickly identify devices of interest by filtering out their own equipment, vehicles, drones, and HQ devices from the scan results.

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

The analyzer starts with a baseline confidence of **50** (neutral) and adjusts based on the following factors:

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

## Session Boundaries

The analyzer defines "early" and "late" boundaries as the first and last **10%** of the session duration:

```
|----10%----|----------------80%-----------------|----10%----|
  EARLY                    MID                        LATE
```

## Examples

### Example 1: SAR Team Radio (Confidence: ~15)

- Present throughout entire session (presence ratio 100%)
- Strong signal at both start and end
- High sighting count

```
Factors:
- High presence ratio (100%) → -30
- Strong RSSI at start (-45) AND end (-42) → -25
- Very high sighting rate (85%) → -15
+ Very strong average signal (-44 dBm) → -5
= Final: 50 - 30 - 25 - 15 - 5 = 0 (capped at 0)
```

### Example 2: Passing Hiker's Phone (Confidence: ~75)

- Appeared only mid-session
- Brief presence (~15 minutes in 2-hour session)
- Low sighting count

```
Factors:
- Low presence ratio (12%) → +15
- Only mid-session appearance → +25
- Low sighting count (4) → +10
= Final: 50 + 15 + 25 + 10 = 100 (capped at 100)
```

### Example 3: HQ Computer (Confidence: ~10)

- Present at boundaries with strong signal
- High presence ratio
- Stationary throughout

```
Factors:
- High presence ratio (100%) → -30
- Strong RSSI at start AND end → -25
+ Low sighting count (but present at boundaries)
= Final: 50 - 30 - 25 = 0 (capped)
```

## Data Requirements

The analyzer requires:

- **BT Devices**: `devices` table with `addr`, `first_seen`, `last_seen`, `confidence`
- **BT Sightings**: `sightings` table with `addr`, `ts_unix`, `rssi`
- **WiFi Devices**: `wifi_devices` table with `mac`, `first_seen`, `last_seen`, `confidence`
- **WiFi Associations**: `wifi_associations` table with `mac`, `ts_unix`, `rssi`

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
    "low_confidence": 38
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
  "updates": {
    "bt_updated": 45,
    "wifi_updated": 23
  },
  "applied": true
}
```

## Customization

The analyzer thresholds can be adjusted by modifying the class constants in `confidence_analyzer.py`:

```python
class ConfidenceAnalyzer:
    BOUNDARY_PERCENT = 0.10       # First/last 10% of session
    STRONG_RSSI_THRESHOLD = -60   # dBm threshold for "strong" signal
    HIGH_PRESENCE_RATIO = 0.80    # >80% = high presence
    MEDIUM_PRESENCE_RATIO = 0.50  # >50% = medium presence
    HIGH_SIGHTING_RATE = 0.70     # >70% of expected cycles
```

## Limitations

1. **Single Session Analysis**: The analyzer treats all data as one continuous session. Multiple search sessions in the same database may produce less accurate results.

2. **No Machine Learning (Yet)**: Currently uses rule-based heuristics. Future versions may incorporate ML models trained on labeled SAR data.

3. **Device Name Ignorance**: Does not factor in device names or manufacturer data, which could provide additional context.

4. **No GPS Clustering**: Does not analyze geographic patterns (e.g., devices always seen at base camp location).

## Future Enhancements

- [ ] Machine learning model trained on historical SAR session data
- [ ] GPS-based clustering to identify stationary vs roaming devices
- [ ] Device name/manufacturer analysis (filter known SAR equipment brands)
- [ ] Multi-session awareness with session boundary detection
- [ ] Configurable team device whitelist
- [ ] Integration with external missing person device databases
