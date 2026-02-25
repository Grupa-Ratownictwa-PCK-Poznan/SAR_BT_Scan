# SAR BT+WiFi Scanner - User Guide

## What Is This?

SAR BT Scanner is a portable device detection system designed for **Search and Rescue (SAR) operations**. It detects wireless signals from phones, smartwatches, fitness trackers, and other Bluetooth/WiFi devices that a missing person might be carrying.

**Key Capabilities:**
- Detects Bluetooth devices within ~50-100 meters
- Captures WiFi probe requests from phones searching for known networks
- Tags all detections with GPS coordinates and timestamps
- Helps differentiate between SAR team equipment and potential target devices
- Triangulates device location and movement patterns
- Provides confidence scoring to prioritize investigation targets

---

## Getting Started

### 1. Power On

Connect your scanner to power. The system will automatically:
- Initialize GPS and wait for satellite fix
- Start scanning for Bluetooth and WiFi devices
- Launch the web dashboard

### 2. Wait for GPS Fix

Before moving into the search area, ensure the GPS indicator shows a fix:
- **3D Fix** (green) - Optimal, full coordinates with altitude
- **2D Fix** (yellow) - Acceptable, no altitude data
- **NO FIX** (red) - Wait for satellites, GPS data will be missing

### 3. Access the Dashboard

On any device connected to the same network, open a web browser and go to:

```
http://<scanner-ip>:8000
```

The IP address is typically shown on the scanner's display or can be found via your router.

---

## Web Dashboard Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  🕐 15:42:38                              [☀️ Theme] [ℹ️ About] [⚙️ Settings] │
├──────────────────────────────║──────────────────────────────────────────────┤
│       SIDEBAR                ║              MAP AREA                        │
│ ┌──────────────────────────┐ ║  ┌──────────────────────────────────────────┐ │
│ │ GPS: 3D Fix ✓  12 sats   │ ║  │                                          │ │
│ │ Mode: Both   WiFi: ON    │ ║  │      🔴🟡🟢  GPS Heatmap                 │ │
│ └──────────────────────────┘ ║  │                                          │ │
│ ┌──────────────────────────┐ ║  │   Red = Strong signal / Many detections  │ │
│ │ BT Devices:     125      │ ║  │   Green = Weak / Few detections          │ │
│ │ WiFi Devices:    89      │ ║  │                                          │ │
│ │ BT Sightings:  2,341     │ ║  │   Click any point for details            │ │
│ │ WiFi Assoc:    1,567     │ ║  │                                          │ │
│ └──────────────────────────┘ ║  └──────────────────────────────────────────┘ │
│ ┌──────────────────────────┐ ║                                               │
│ │ Filters:                 │ ║  Map Controls:                                │
│ │ [MAC    ] [SSID   ]      │ ║  [BT Only] [WiFi Only] [Both]                │
│ │ RSSI: ─●────── -60 dBm   │ ║                                               │
│ │ Confidence: ──●── 50%    │ ║                                               │
│ └──────────────────────────┘ ║                                               │
│ ┌──────────────────────────┐ ║                                               │
│ │[BT Dev][BT Sight][WiFi D]│ ║                                               │
│ │ MAC      │ Name │ Conf   │ ║                                               │
│ │ AA:BB:.. │ iPho │  72    │ ║                                               │
│ │ 11:22:.. │ Fitb │  35    │ ║                                               │
│ │ (click row for details)  │ ║                                               │
│ └──────────────────────────┘ ║                                               │
│ ┌──────────────────────────┐ ║                                               │
│ │ 📥 Download DB           │ ║                                               │
│ │ 🗑️  Purge DB              │ ║                                               │
│ │ 📊 Analyze Confidence    │ ║                                               │
│ │ 📍 (Device Triangulation)│ ║                                               │
│ └──────────────────────────┘ ║                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Status Panel (Top)

| Indicator | Meaning |
|-----------|---------|
| **GPS** | Satellite fix status and count |
| **Mode** | Current scan mode (BT/WiFi/Both) |
| **WiFi Mon** | WiFi monitor mode active (ON/OFF) |
| **Time** | Current UTC time |

### Data Tabs

| Tab | Content |
|-----|--------|
| **BT Devices** | Unique Bluetooth devices detected with manufacturer and notes |
| **BT Sightings** | Individual detection events with RSSI |
| **WiFi Devices** | Unique WiFi MAC addresses with vendor name and device type |
| **WiFi Assoc** | WiFi probe requests with SSIDs |

### Map View

The map shows a heatmap of detection locations:
- **Red/Orange areas** = Many detections (likely SAR team positions)
- **Blue/Green areas** = Fewer detections (potentially interesting)

Use the layer toggle to switch between BT-only, WiFi-only, or combined view.

### Theme Toggle

The dashboard supports both light and dark themes:
- **Light Mode** (☀️): Default, Red Cross branded colors
- **Dark Mode** (🌙): Reduced eye strain for low-light field conditions

Toggle via the theme button in the header.

### Interactive Device Details

Click any row in the device tables to open a detailed popup:

```
┌────────────────────────────────────────────────────────┐
│ DEVICE DETAILS                               [✕ Close] │
├────────────────────────────────────────────────────────┤
│ MAC Address:    AA:BB:CC:DD:EE:FF                      │
│ Device Type:    Bluetooth                              │
│ Name:           iPhone                                 │
│ Manufacturer:   Apple Inc.                             │
│ Confidence:     72%                                    │
│ First Seen:     2026-02-25 08:15:32                    │
│ Last Seen:      2026-02-25 14:22:45                    │
├────────────────────────────────────────────────────────┤
│ ASSOCIATED SSIDs (WiFi devices):                       │
│  • Home_Network (15 attempts)                          │
│  • Office_WiFi (3 attempts)                            │
├────────────────────────────────────────────────────────┤
│ ANALYST NOTES:                                         │
│ ┌────────────────────────────────────────────────────┐ │
│ │ Seen near northwest perimeter at 14:20            │ │
│ │ Possible match to missing person's device         │ │
│ └────────────────────────────────────────────────────┘ │
│ [Save Notes] [Cancel]                                  │
├────────────────────────────────────────────────────────┤
│ [📍 Analyze Location - Triangulate this device]        │
└────────────────────────────────────────────────────────┘
```

---

## WiFi Device Identification

The dashboard automatically identifies WiFi devices using the IEEE OUI (Organizationally Unique Identifier) database:

- **Vendor**: Manufacturer name looked up from MAC address prefix (e.g., "Apple, Inc", "Cisco Systems")
- **Device Type**: Heuristic guess based on vendor and MAC pattern (e.g., "phone", "network", "iot")

These fields help quickly identify device categories without additional setup. The OUI database contains 38,904 vendor entries and can be updated anytime via the **"Update OUI Database"** button in the sidebar.

---

## Analyst Notes

Both Bluetooth and WiFi device tables include a **Notes** column where analysts can add custom annotations:

- Use notes to flag interesting findings
- Example: "Seen near search zone perimeter"
- Example: "Matches missing person's known networks"
- Notes persist across sessions and appear in exported reports

Edit notes by:
1. Clicking a device row to open the details popup
2. Typing in the Notes textarea
3. Clicking "Save Notes"

---

## Device Triangulation

The triangulation feature analyzes all sightings for a device to determine its location and movement patterns.

### Accessing Triangulation

1. Click any device row to open the details popup
2. Click **"Analyze Location"** button
3. Or navigate directly: `http://<scanner-ip>:8000/triangulate?mac=AA:BB:CC:DD:EE:FF`

### Triangulation Page Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 📍 DEVICE TRIANGULATION - AA:BB:CC:DD:EE:FF              [← Back] [🔄 Refresh]│
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────┐   ┌───────────────────────────────────────────┐│
│  │ DEVICE INFO             │   │                                           ││
│  │ MAC: AA:BB:CC:DD:EE:FF  │   │          MOVEMENT MAP                     ││
│  │ Type: Bluetooth         │   │                                           ││
│  │ Confidence: 75%         │   │   🔵 First seen    🟢 Last seen           ││
│  ├─────────────────────────┤   │   - - - Movement path                     ││
│  │ MOVEMENT ANALYSIS       │   │   ● Location clusters                     ││
│  │ Status: MOVING          │   │                                           ││
│  │ Total Distance: 1.5 km  │   │                                           ││
│  │ Avg Speed: 0.25 km/h    │   └───────────────────────────────────────────┘│
│  ├─────────────────────────┤                                                │
│  │ PRIMARY LOCATION        │   ┌───────────────────────────────────────────┐│
│  │ Lat: 52.408100          │   │ SIGHTINGS TIMELINE                        ││
│  │ Lon: 16.928500          │   │ 08:15 ●━━━●━━━━━●━━━━━━━━━━━━●━━━━● 14:22 ││
│  │ [Open in Google Maps]   │   │       C1    C2              C3      C4    ││
│  └─────────────────────────┘   └───────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

### Understanding Triangulation Results

| Metric | Description |
|--------|-------------|
| **Status** | MOVING or STATIONARY based on location variance |
| **Movement Confidence** | How certain the analysis is (higher = more data) |
| **Total Distance** | Sum of all movement segments |
| **Location Clusters** | Groups of nearby sightings (device stayed in area) |
| **Primary Location** | Most likely current/last position |

### When to Use Triangulation

- **High-confidence devices** (70+): Triangulate to find location
- **Moving devices**: Track path to predict direction
- **Brief appearances**: Find where device was seen
- **Cluster analysis**: See if device stayed in one area

---

## Understanding Confidence Scores

Each device gets a **confidence score from 0-100** indicating how likely it belongs to a missing person versus SAR team equipment.

### Score Ranges

| Score | Interpretation | Action |
|-------|----------------|--------|
| **70-100** | Possibly missing person's device | Investigate immediately |
| **31-69** | Uncertain origin | Review details |
| **0-30** | Likely SAR team equipment | Lower priority |

### What Affects the Score?

**Lower scores (likely SAR team):**
- Device present throughout entire session
- Strong signal at both session start and end
- Always detected near HQ/staging area
- Seen across multiple search sessions

**Higher scores (possibly target):**
- Device appeared only mid-session
- Brief detection window
- Detected far from HQ location
- Never seen before

### Running Analysis

1. Click the **"Analyze Confidence"** button in the sidebar
2. Review the preview showing proposed score changes
3. Click **"Apply Changes"** to update scores
4. Filter the device list by confidence to focus on high-priority targets

### Enriching WiFi Device Data

The confidence analyzer automatically enriches WiFi device data during analysis:

- Looks up vendor names using IEEE OUI database
- Guesses device type based on vendor patterns
- Stores enrichment results for persistence

Use the **"Update OUI Database"** button to sync the latest vendor data before running analysis.

---

## Managing Team Devices (Whitelist)

To exclude your team's known devices from analysis:

### Adding Devices to Whitelist

Edit the `device_whitelist.txt` file on the scanner:

```text
# SAR Team Equipment
# Add one MAC address per line

# Team Leader phone
AA:BB:CC:DD:EE:FF

# SAR vehicle tracker
11:22:33:44:55:66

# Drone controller
AA:BB:CC:11:22:33
```

Whitelisted devices automatically receive confidence score = 0.

### Finding Your Device's MAC

- **iPhone**: Settings → General → About → WiFi Address
- **Android**: Settings → About Phone → Status → WiFi MAC Address
- **Bluetooth devices**: Check device packaging or companion app

---

## Field Operations

### Before Deployment

1. **Charge fully** - Scanner runs ~8 hours on 10,000mAh powerbank
2. **Test GPS fix** - Ensure satellites lock before leaving staging area
3. **Update whitelist** - Add all team device MACs
4. **Update OUI database** - Click "Update OUI Database" button for latest vendor data (optional but recommended)
5. **Set HQ coordinates** - Configure staging area location in settings (optional)
6. **Verify web access** - Confirm dashboard loads on your phone/tablet

### During Search

1. **Move steadily** - Walk at normal pace, pausing briefly in key areas
2. **Note signal strength** - Strong signals (> -60 dBm) indicate nearby devices
3. **Watch for mid-session appearances** - New devices appearing during search are interesting
4. **Mark locations** - Note GPS coordinates of significant detections

### Common Detection Scenarios

| Scenario | What It Might Mean |
|----------|-------------------|
| Strong signal, stationary | Device is nearby, possibly stationary person |
| Weak signal, moving | Device at distance, or person moving |
| Device appears then disappears | Person passed through area |
| WiFi probing for home network | Device owner lives at that network location |

### After Search

1. **Run confidence analysis** to score all devices
2. **Export data** for mission report
3. **Clear database** before next mission (optional)
4. **Backup database file** for records

---

## Filtering and Finding Devices

### By MAC Address

Enter partial MAC in the filter box:
- `AA:BB` finds all MACs starting with AA:BB
- `EE:FF` finds all MACs ending with EE:FF

### By Signal Strength

Use the RSSI slider to focus on:
- **Strong signals (> -60 dBm)**: Devices within ~10 meters
- **Medium signals (-60 to -80 dBm)**: Devices 10-30 meters away
- **Weak signals (< -80 dBm)**: Distant devices, 30+ meters

### By Time

Use the time filter to:
- Remove noisy startup period
- Focus on specific search windows
- Isolate times when interesting activity occurred

### By Confidence

Filter by confidence score to:
- Show only high-confidence (70+) potential targets
- Hide likely SAR equipment (0-30)

---

## Do's and Don'ts

### DO ✅

- **DO** add all team devices to the whitelist before deployment
- **DO** wait for GPS fix before starting search
- **DO** run confidence analysis periodically during long searches
- **DO** note the time and location when you see interesting devices
- **DO** charge the scanner fully before each mission
- **DO** keep the scanner with you (not in a vehicle) for better coverage
- **DO** check web dashboard periodically for high-confidence alerts
- **DO** document and backup data after each mission

### DON'T ❌

- **DON'T** use this tool for any purpose other than SAR operations
- **DON'T** track people who are not officially missing
- **DON'T** share scan data with unauthorized parties
- **DON'T** assume all high-confidence devices belong to the missing person
- **DON'T** ignore weak signals - they might indicate distant targets
- **DON'T** run the scanner without GPS - you'll lose location data
- **DON'T** forget to clear the database between unrelated missions
- **DON'T** position scanner in metal containers or vehicles (reduces range)

---

## Troubleshooting

### GPS shows "NO FIX"

- Move to open sky area (away from buildings/trees)
- Wait 2-3 minutes for satellite acquisition
- Check GPS dongle is firmly connected

### Web dashboard won't load

- Verify scanner is powered on
- Check you're on the same network
- Try the IP address directly (not hostname)
- Check if `WEB_UI_ENABLED = True` in settings

### No devices appearing

- Confirm scan mode includes BT and/or WiFi
- For WiFi: verify monitor mode is enabled
- Check Bluetooth adapter is connected
- Move to area with more wireless activity

### All devices show confidence = 50

- Run "Analyze Confidence" from the dashboard
- Ensure session has enough data (10+ minutes)
- Check that analysis completed successfully

### Battery draining quickly

- Normal consumption is ~5W
- Expected runtime: ~8 hours on 10,000mAh
- Reduce screen brightness on connected devices
- Consider larger powerbank for extended operations

---

## Data Privacy and Ethics

This tool is designed **exclusively for Search and Rescue operations**. 

### Permitted Uses
- Active SAR operations for missing persons
- Training exercises with team equipment only
- Testing and development with consent

### Prohibited Uses
- Tracking family members, partners, or acquaintances
- Surveillance of any kind
- Monitoring employees or neighbors
- Any use targeting non-missing persons

**The ethical justification for this tool exists only when there is genuine risk to human life.**

For complete ethical guidelines, see [ETHICS.md](ETHICS.md).

---

## Quick Reference Card

### Key Actions

| Action | How |
|--------|-----|
| View devices | Open web dashboard, click "BT Devices" or "WiFi Devices" tab |
| Filter by signal | Adjust RSSI slider in filters panel |
| Analyze scores | Click "Analyze Confidence" → Review → Apply |
| Add team device | Edit `device_whitelist.txt`, add MAC address |
| Find strong signals | Filter RSSI > -60 dBm |
| Find new devices | Sort by "First Seen" descending |
| Focus on targets | Filter confidence ≥ 70 |
| View device details | Click any row in device table |
| Add notes | Click device → Edit notes in popup → Save |
| Triangulate device | Click device → "Analyze Location" button |
| Toggle theme | Click ☀️/🌙 button in header |
| Download database | Click "Download DB" in sidebar |
| Clear data | Click "Purge DB" (creates backup first) |

### Confidence Score Summary

```
0-30   = Likely SAR team (whitelist or always present)
31-69  = Unknown, needs investigation
70-100 = Possible target (appeared mid-session, far from HQ)
```

### Signal Strength Guide

```
> -50 dBm  = Very close (< 5m)
-50 to -60 = Close (5-10m)
-60 to -70 = Medium (10-20m)
-70 to -80 = Far (20-30m)
< -80 dBm  = Very far (30m+)
```

---

## Getting Help

- **Technical issues**: Check [README.md](README.md) and [WEB_UI_QUICKSTART.md](docs/WEB_UI_QUICKSTART.md)
- **Confidence scoring**: See [CONFIDENCE_ANALYZER.md](docs/CONFIDENCE_ANALYZER.md)
- **Device triangulation**: See [TRIANGULATION.md](docs/TRIANGULATION.md)
- **WiFi setup**: See [WIFI_SETUP.md](docs/WIFI_SETUP.md)
- **Project repository**: https://github.com/Grupa-Ratownictwa-PCK-Poznan/SAR_BT_Scan

---

*This tool was developed by Grupa Ratownictwa PCK Poznań to support humanitarian Search and Rescue operations.*
