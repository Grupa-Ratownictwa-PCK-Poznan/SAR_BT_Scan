# Device Type Classifier

## Overview

The Device Type Classifier (`device_type_classifier.py`) provides expanded device categorization during the analysis phase. It combines multiple signals — BLE service UUIDs, device names, manufacturer names, OUI vendor lookups, WiFi SSIDs, beacon status, and MAC address properties — to classify each discovered device into one of **21 categories**.

The classifier is called automatically by the **Confidence Analyzer** after scanning is complete. It does **not** modify the scanner logic or database schema.

## Categories

| Category | Description | Examples |
|----------|-------------|----------|
| `phone` | Smartphones | iPhone, Galaxy S, Pixel, OnePlus |
| `router` | WiFi APs, routers, mesh nodes | Cisco, Ubiquiti, TP-Link APs, Eero |
| `wearable` | Smartwatches, fitness bands | Apple Watch, Fitbit, Garmin Fenix, Mi Band |
| `headphones` | Earbuds, over-ear headphones, headsets | AirPods, Bose QC, Sony WH, Galaxy Buds |
| `hearing_aid` | BLE hearing aids | ReSound, Phonak, Oticon, Widex, Signia |
| `pacemaker` | Implantable cardiac devices | Biotronik, CRT-D, CRT-P |
| `insulin_pump` | Insulin pumps and CGMs | OmniPod, Dexcom G7, FreeStyle Libre, MiniMed |
| `drone` | UAVs and controllers | DJI Mavic, Parrot Anafi, Skydio, Autel EVO |
| `sar_device` | SAR/emergency radios, GPS, thermal cameras | Garmin inReach, Kenwood, Baofeng, FLIR |
| `iot` | Smart home sensors, mesh, dev boards | Philips Hue, ESP32, Tuya, Sonoff, Zigbee |
| `tv` | Smart TVs, streaming sticks | Samsung TV, Chromecast, Roku, Fire TV |
| `home_appliance` | Robot vacuums, kitchen devices, scales | Roomba, Roborock, Thermomix, Dyson |
| `civil_infrastructure` | Smart meters, traffic controllers | Smart Meter, SCADA, Parking Meter |
| `computer` | Laptops, desktops | MacBook, ThinkPad, Dell XPS, Chromebook |
| `tablet` | Tablets, e-readers | iPad, Galaxy Tab, Surface Pro, Kindle |
| `tracker` | Bluetooth trackers | AirTag, Tile, SmartTag, Chipolo |
| `audio` | Speakers, sound bars, smart speakers | Sonos, JBL Flip, HomePod, Echo Dot |
| `camera` | Action cameras, IP cameras | (name-based heuristic) |
| `printer` | Printers, MFPs | Canon Pixma, HP OfficeJet, Brother MFC |
| `automotive` | Car infotainment, OBD dongles | Tesla, CarPlay, Android Auto |
| `medical` | Pulse oximeters, BP monitors, other | Masimo, GE Healthcare, Omron |

## Sure Match vs Heuristic

- **No suffix** (e.g., `headphones`) — high-confidence classification based on strong signals like BLE service UUIDs or unambiguous device names.
- **`[heur]` suffix** (e.g., `phone [heur]`) — heuristic guess based on weaker or ambiguous signals (vendor OUI, partial name match, randomized MAC fallback).

## Classification Priority

The classifier evaluates signals in order of strength. The first match wins:

```
1. BLE Service UUID         (strongest — sure match)
2. Device name keywords      (sure or [heur] per rule)
3. WiFi SSID patterns        (before beacon fallback — prevents phone hotspot misclassification)
4. WiFi beacon → router      (generic AP fallback — sure if known vendor, else [heur])
5. Vendor/manufacturer OUI   (always [heur])
6. Randomized MAC fallback   (→ phone [heur])
```

### 1. BLE Service UUID (Strongest)

Standard BLE GATT service UUIDs provide definitive classification:

| UUID (16-bit) | Category | Service |
|---------------|----------|---------|
| `0xFDF0` | hearing_aid | ASHA (Audio Streaming for Hearing Aid) |
| `0x1854` | hearing_aid | HAP (Hearing Access Profile) |
| `0x183A` | insulin_pump | Insulin Delivery Service |
| `0x1808` | insulin_pump | Glucose Service (CGM) |
| `0x1822` | medical | Pulse Oximeter |
| `0x1810` | medical | Blood Pressure |
| `0x180D` | wearable | Heart Rate |
| `0x184E` | headphones | Audio Stream Control (LE Audio) |
| `0x1844` | headphones | Volume Control |
| `0x1827` | iot | Mesh Provisioning |
| `0x181A` | iot | Environmental Sensing |
| `0x181D` | home_appliance | Weight Scale |
| `0x1819` | sar_device | Location and Navigation |
| `0x1803` | tracker | Link Loss |

### 2. Device Name Keywords

~200 keyword rules across all categories, checked case-insensitively against the combined BLE name + manufacturer + OUI vendor string. Each rule specifies whether it's a sure match or heuristic.

Examples:
- `"airpods"` → `headphones` (sure)
- `"apple watch"` → `wearable` (sure)
- `"dexcom"` → `insulin_pump` (sure)
- `"nokia"` → `phone [heur]` (heuristic — could be other Nokia products)
- `"drone"` → `drone [heur]` (heuristic — generic keyword)

### 3. WiFi SSID Patterns

WiFi SSIDs are checked before the generic beacon→router fallback. This ensures that phone hotspots (e.g., a beacon with SSID "iPhone") are correctly classified as phones.

| SSID Pattern | Category | Notes |
|-------------|----------|-------|
| `DJI-*` | drone | Sure if beacon |
| `iphone` | phone | Sure if beacon |
| `androidap` | phone | Sure if beacon |
| `ubnt`, `unifi`, `meraki` | router | Sure if beacon |
| `tuya-*`, `esp_*` | iot | Sure if beacon |
| `chromecast`, `firetv` | tv | Sure if beacon |

### 4. WiFi Beacon Fallback

Any WiFi device emitting only Beacon frames (not Probe Requests) that wasn't matched by SSIDs is classified as a router. If the OUI vendor matches a known networking vendor (Cisco, Ubiquiti, etc.), it's a sure match; otherwise `router [heur]`.

### 5. Vendor/Manufacturer Heuristics

OUI vendor and BLE manufacturer names are checked against ~140 vendor keywords. Always returns `[heur]` suffix since the same vendor can make many product types.

### 6. Randomized MAC Fallback

If no other signal provides a match but the MAC is locally-administered (randomized), the device is classified as `phone [heur]`, since randomized MACs are almost exclusively used by modern smartphones.

## Integration with Confidence Analyzer

The classifier is called during `analyze_bt_device()` and `analyze_wifi_device()` in `confidence_analyzer.py`:

### Bluetooth Devices

Signals used: BLE name, BLE manufacturer, service UUIDs (collected from all sightings), OUI vendor, MAC randomization.

The classified type is stored in the `guessed_type` field of `DeviceAnalysis` and persisted to the `notes` column of the `devices` table as a `[type:...]` tag:

```
[type:headphones] User-added notes here
```

### WiFi Devices

Signals used: OUI vendor, SSIDs (probed or broadcast), beacon status, MAC randomization.

The classified type is stored in the `device_type` column of the `wifi_devices` table (replacing the simpler OUI-only guess from `wifi_oui_lookup.py`).

## Usage

### Programmatic

```python
from device_type_classifier import classify_device

# BLE device with service UUID
classify_device(service_uuids=['0000fdf0-0000-1000-8000-00805f9b34fb'])
# → "hearing_aid"

# BLE device by name
classify_device(name='AirPods Pro', manufacturer='Apple, Inc.')
# → "headphones"

# WiFi access point
classify_device(oui_vendor='Cisco Systems', is_beacon=True)
# → "router"

# Phone hotspot (beacon + SSID)
classify_device(ssids=['iPhone-hotspot'], is_beacon=True)
# → "phone"

# Only a randomized MAC available
classify_device(is_randomized_mac=True)
# → "phone [heur]"

# No signals at all
classify_device()
# → ""
```

### Via Confidence Analyzer CLI

Device types appear in verbose output:

```bash
python confidence_analyzer.py -v --dry-run
```

```
[BT] AA:BB:CC:DD:EE:FF
  Confidence: 50 → 82
  BT Name: AirPods Pro
  BT Manufacturer: Apple, Inc.
  Device Type: headphones
  Factors:
    - Personal device identified (AirPods Pro / Apple, Inc.) → +12
    ...
```

## SAR Relevance

In Search and Rescue context, the expanded classification helps teams:

- **Quickly identify personal devices** (phones, wearables, headphones) that may belong to a missing person
- **Filter out infrastructure** (routers, civil infrastructure, IoT) and SAR team equipment (drones, radios)
- **Spot medical devices** (hearing aids, insulin pumps, pacemakers) which are strong indicators of a person's presence and may inform rescue approach
- **Distinguish operational assets** (drones, SAR radios) from search targets

## Extending the Classifier

To add new device types or keywords, edit `device_type_classifier.py`:

1. **New BLE service UUID** → add to `_SERVICE_UUID_TYPES` dict
2. **New name keyword** → add to `_NAME_RULES` list (specify `True` for sure match, `False` for heuristic)
3. **New WiFi SSID pattern** → add to `_SSID_RULES` list
4. **New vendor heuristic** → add to `_VENDOR_HEURISTICS` list

The classifier is a pure function with no side effects — changes take effect immediately on the next analysis run.
