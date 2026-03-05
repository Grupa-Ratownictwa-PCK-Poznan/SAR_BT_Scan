#!/usr/bin/env python3
"""
Device Type Classifier for SAR Scanner

Rich device classification that combines multiple signals available during
the analysis phase:
  - BLE advertised name and manufacturer (from BT SIG company ID)
  - BLE GATT service UUIDs (from sightings table)
  - WiFi OUI vendor name (from MAC prefix lookup)
  - WiFi SSIDs (probed or broadcast)
  - WiFi packet type (Beacon = AP, ProbeRequest = client)
  - MAC address properties (randomization)

Output categories:
  phone             – smartphones (iPhone, Galaxy, Pixel, …)
  router            – WiFi APs, routers, mesh nodes
  wearable          – smartwatches, fitness bands
  headphones        – earbuds, over-ear headphones, headsets
  hearing_aid       – BLE hearing aids (ASHA / HAP)
  pacemaker         – implantable cardiac devices
  insulin_pump      – insulin pumps and CGMs
  drone             – UAVs (DJI, Parrot, Skydio, …)
  sar_device        – SAR/emergency radios, GPS beacons, thermal cameras
  iot               – smart home sensors, mesh devices, dev boards
  tv                – smart TVs, streaming sticks
  home_appliance    – robot vacuums, kitchen devices, scales
  civil_infrastructure – smart meters, traffic controllers, street lights
  computer          – laptops, desktops
  tablet            – iPad, Android tablets, Kindle
  tracker           – AirTag, Tile, SmartTag
  audio             – Bluetooth speakers, smart speakers, sound bars
  camera            – action cameras, IP cameras
  printer           – printers, MFPs
  automotive        – car infotainment, OBD dongles
  medical           – pulse oximeters, blood-pressure monitors, other med devices

Suffix "[heur]" indicates a heuristic guess based on weaker/ambiguous signals.
No suffix = high-confidence classification based on strong indicators.

Usage:
    from device_type_classifier import classify_device
    dtype = classify_device(name="AirPods Pro", manufacturer="Apple, Inc.")
    # → "headphones"
"""

from typing import Optional, List


# ═══════════════════════════════════════════════════════════════════════════
# 1. BLE Service UUID → device type  (strongest signal, sure match)
# ═══════════════════════════════════════════════════════════════════════════
# Keys are the 16-bit UUID hex (lowercase, without 0x prefix).
# Standard BLE 128-bit UUIDs embed the 16-bit value at positions [4:8]:
#   0000XXXX-0000-1000-8000-00805f9b34fb
_SERVICE_UUID_TYPES = {
    # ── Hearing aids ──────────────────────────────────────────────────────
    "fdf0": "hearing_aid",          # ASHA  (Audio Streaming for Hearing Aid)
    "1854": "hearing_aid",          # HAP   (Hearing Access Profile)
    "1857": "hearing_aid",          # HAS   (Hearing Aid Service)

    # ── Insulin / glucose ─────────────────────────────────────────────────
    "183a": "insulin_pump",         # Insulin Delivery Service
    "1808": "insulin_pump",         # Glucose Service  (CGM / pump combo)

    # ── Other medical ─────────────────────────────────────────────────────
    "1822": "medical",              # Pulse Oximeter
    "1810": "medical",              # Blood Pressure

    # ── Fitness / wearable ────────────────────────────────────────────────
    "180d": "wearable",             # Heart Rate
    "1816": "wearable",             # Cycling Speed and Cadence
    "1814": "wearable",             # Running Speed and Cadence
    "183e": "wearable",             # Physical Activity Monitor

    # ── LE Audio (headphones / speakers) ──────────────────────────────────
    "184e": "headphones",           # Audio Stream Control Service
    "184f": "headphones",           # Broadcast Audio Scan Service
    "1850": "headphones",           # Media Control Service
    "1844": "headphones",           # Volume Control Service

    # ── IoT / Mesh ────────────────────────────────────────────────────────
    "1827": "iot",                  # Mesh Provisioning Service
    "1828": "iot",                  # Mesh Proxy Service
    "181a": "iot",                  # Environmental Sensing
    "1815": "iot",                  # Automation IO
    "1820": "iot",                  # Internet Protocol Support
    "183b": "iot",                  # Binary Sensor

    # ── Home appliance (scales) ───────────────────────────────────────────
    "181d": "home_appliance",       # Weight Scale
    "181b": "home_appliance",       # Body Composition

    # ── SAR / navigation ──────────────────────────────────────────────────
    "1819": "sar_device",           # Location and Navigation
    "183c": "sar_device",           # Emergency Configuration

    # ── Tracker ───────────────────────────────────────────────────────────
    "1803": "tracker",              # Link Loss (often trackers / proximity tags)
}


# ═══════════════════════════════════════════════════════════════════════════
# 2. Name-based rules (BLE name + manufacturer + OUI vendor combined)
# ═══════════════════════════════════════════════════════════════════════════
# Tuples: (keyword, device_type, sure_match)
# Checked case-insensitively.  First match wins → order by specificity.
_NAME_RULES: list[tuple[str, str, bool]] = [
    # ── Hearing aids (sure) ───────────────────────────────────────────────
    ("hearing aid",     "hearing_aid", True),
    ("resound",         "hearing_aid", True),
    ("phonak",          "hearing_aid", True),
    ("oticon",          "hearing_aid", True),
    ("widex",           "hearing_aid", True),
    ("signia",          "hearing_aid", True),
    ("starkey",         "hearing_aid", True),
    ("unitron",         "hearing_aid", True),
    ("bernafon",        "hearing_aid", True),
    ("rexton",          "hearing_aid", True),
    ("cochlear",        "hearing_aid", True),

    # ── Pacemaker / implantable cardiac devices ───────────────────────────
    ("pacemaker",       "pacemaker", True),
    ("cardiac monitor", "pacemaker", False),
    ("crt-d",           "pacemaker", True),
    ("crt-p",           "pacemaker", True),
    ("implantable",     "pacemaker", False),
    ("biotronik",       "pacemaker", True),
    ("livanova",        "pacemaker", False),

    # ── Insulin pumps / CGM ───────────────────────────────────────────────
    ("omnipod",         "insulin_pump", True),
    ("dexcom",          "insulin_pump", True),
    ("freestyle libre", "insulin_pump", True),
    ("tslim",           "insulin_pump", True),
    ("insulet",         "insulin_pump", True),
    ("minimed",         "insulin_pump", True),
    ("medtronic guardian", "insulin_pump", True),
    ("medtronic 770",   "insulin_pump", True),
    ("medtronic 780",   "insulin_pump", True),
    ("insulin",         "insulin_pump", True),
    ("libre",           "insulin_pump", False),
    ("tandem diabetes", "insulin_pump", True),
    ("cgm",             "insulin_pump", False),

    # ── Drones ────────────────────────────────────────────────────────────
    ("dji",             "drone", True),
    ("mavic",           "drone", True),
    ("matrice",         "drone", True),
    ("parrot anafi",    "drone", True),
    ("parrot bebop",    "drone", True),
    ("parrot disco",    "drone", True),
    ("skydio",          "drone", True),
    ("autel evo",       "drone", True),
    ("autel robotics",  "drone", True),
    ("quadcopter",      "drone", True),
    ("phantom",         "drone", False),
    ("drone",           "drone", False),
    ("fpv",             "drone", False),
    ("uav",             "drone", False),

    # ── Headphones / earbuds ──────────────────────────────────────────────
    ("airpods",         "headphones", True),
    ("airpod",          "headphones", True),
    ("beats fit",       "headphones", True),
    ("beats solo",      "headphones", True),
    ("beats studio",    "headphones", True),
    ("beats flex",      "headphones", True),
    ("powerbeats",      "headphones", True),
    ("bose qc",         "headphones", True),
    ("bose quietcomfort","headphones", True),
    ("bose noise",      "headphones", True),
    ("bose soundsport", "headphones", True),
    ("bose sport",      "headphones", True),
    ("bose 700",        "headphones", True),
    ("sony wh-",        "headphones", True),
    ("sony wf-",        "headphones", True),
    ("sony mdr-",       "headphones", True),
    ("jabra elite",     "headphones", True),
    ("jabra evolve",    "headphones", True),
    ("jabra talk",      "headphones", True),
    ("galaxy buds",     "headphones", True),
    ("buds pro",        "headphones", True),
    ("buds live",       "headphones", True),
    ("buds2",           "headphones", True),
    ("buds fe",         "headphones", True),
    ("pixel buds",      "headphones", True),
    ("jbl tune",        "headphones", True),
    ("jbl live",        "headphones", True),
    ("jbl reflect",     "headphones", True),
    ("jbl endurance",   "headphones", True),
    ("jbl free",        "headphones", True),
    ("sennheiser momentum", "headphones", True),
    ("sennheiser cx",   "headphones", True),
    ("sennheiser hd",   "headphones", True),
    ("sennheiser pxc",  "headphones", True),
    ("marshall major",  "headphones", True),
    ("marshall mid",    "headphones", True),
    ("marshall monitor","headphones", True),
    ("audio-technica ath", "headphones", True),
    ("earbuds",         "headphones", True),
    ("earphone",        "headphones", True),
    ("headphone",       "headphones", True),
    ("headset",         "headphones", False),

    # ── Wearables / watches ───────────────────────────────────────────────
    ("apple watch",     "wearable", True),
    ("iwatch",          "wearable", True),
    ("galaxy watch",    "wearable", True),
    ("gear s",          "wearable", True),
    ("gear fit",        "wearable", True),
    ("galaxy fit",      "wearable", True),
    ("fitbit",          "wearable", True),
    ("mi band",         "wearable", True),
    ("mi smart band",   "wearable", True),
    ("amazfit",         "wearable", True),
    ("huawei band",     "wearable", True),
    ("huawei watch",    "wearable", True),
    ("honor band",      "wearable", True),
    ("garmin fenix",    "wearable", True),
    ("garmin forerunner","wearable", True),
    ("garmin venu",     "wearable", True),
    ("garmin vivoactive","wearable", True),
    ("garmin vivosmart","wearable", True),
    ("garmin instinct", "wearable", True),
    ("garmin enduro",   "wearable", True),
    ("garmin lily",     "wearable", True),
    ("garmin descent",  "wearable", True),
    ("suunto",          "wearable", True),
    ("polar vantage",   "wearable", True),
    ("polar grit",      "wearable", True),
    ("polar ignite",    "wearable", True),
    ("polar unite",     "wearable", True),
    ("coros pace",      "wearable", True),
    ("coros vertix",    "wearable", True),
    ("coros apex",      "wearable", True),
    ("whoop",           "wearable", True),
    ("oura ring",       "wearable", True),
    ("ticwatch",        "wearable", True),
    ("fossil gen",      "wearable", True),
    ("fossil hr",       "wearable", True),
    ("smartwatch",      "wearable", True),
    ("smart watch",     "wearable", True),
    ("oura",            "wearable", False),
    ("withings",        "wearable", False),
    ("polar m",         "wearable", False),

    # ── Phones ────────────────────────────────────────────────────────────
    ("iphone",          "phone", True),
    ("galaxy s2",       "phone", True),
    ("galaxy a",        "phone", True),
    ("galaxy z",        "phone", True),
    ("galaxy note",     "phone", True),
    ("pixel phone",     "phone", True),
    ("pixel 6",         "phone", True),
    ("pixel 7",         "phone", True),
    ("pixel 8",         "phone", True),
    ("pixel 9",         "phone", True),
    ("oneplus",         "phone", True),
    ("huawei mate",     "phone", True),
    ("realme",          "phone", True),
    ("oppo",            "phone", True),
    ("motorola moto",   "phone", True),
    ("sony xperia",     "phone", True),
    ("samsung phone",   "phone", True),
    ("nokia",           "phone", False),
    ("huawei p",        "phone", False),
    ("xiaomi",          "phone", False),
    ("redmi",           "phone", False),
    ("vivo",            "phone", False),
    ("htc",             "phone", False),

    # ── Tablets ───────────────────────────────────────────────────────────
    ("ipad",            "tablet", True),
    ("galaxy tab",      "tablet", True),
    ("surface pro",     "tablet", True),
    ("kindle",          "tablet", True),
    ("fire tablet",     "tablet", True),
    ("tab s",           "tablet", False),

    # ── Computers / laptops ───────────────────────────────────────────────
    ("macbook",         "computer", True),
    ("imac",            "computer", True),
    ("thinkpad",        "computer", True),
    ("dell xps",        "computer", True),
    ("surface laptop",  "computer", True),
    ("chromebook",      "computer", True),
    ("laptop",          "computer", False),

    # ── Trackers ──────────────────────────────────────────────────────────
    ("airtag",          "tracker", True),
    ("smarttag",        "tracker", True),
    ("tile mate",       "tracker", True),
    ("tile pro",        "tracker", True),
    ("tile slim",       "tracker", True),
    ("tile sticker",    "tracker", True),
    ("chipolo",         "tracker", True),
    ("tile",            "tracker", False),
    ("find my",         "tracker", False),

    # ── TV / streaming ────────────────────────────────────────────────────
    ("samsung tv",      "tv", True),
    ("[tv]",            "tv", True),
    ("lg tv",           "tv", True),
    ("lg webos",        "tv", True),
    ("android tv",      "tv", True),
    ("google tv",       "tv", True),
    ("roku",            "tv", True),
    ("chromecast",      "tv", True),
    ("fire tv",         "tv", True),
    ("fire stick",      "tv", True),
    ("apple tv",        "tv", True),
    ("nvidia shield",   "tv", True),
    ("smart tv",        "tv", True),
    ("samsung frame",   "tv", True),

    # ── Home appliances ───────────────────────────────────────────────────
    ("roomba",          "home_appliance", True),
    ("irobot",          "home_appliance", True),
    ("roborock",        "home_appliance", True),
    ("thermomix",       "home_appliance", True),
    ("nespresso",       "home_appliance", True),
    ("instant pot",     "home_appliance", True),
    ("ecovacs",         "home_appliance", True),
    ("samsung washer",  "home_appliance", True),
    ("lg washer",       "home_appliance", True),
    ("washing machine", "home_appliance", True),
    ("dishwasher",      "home_appliance", True),
    ("refrigerator",    "home_appliance", True),
    ("fridge",          "home_appliance", True),
    ("vacuum",          "home_appliance", True),
    ("dyson",           "home_appliance", False),
    ("breville",        "home_appliance", False),
    ("shark",           "home_appliance", False),
    ("oven",            "home_appliance", False),

    # ── Routers / APs (name-based) ────────────────────────────────────────
    ("router",          "router", True),
    ("access point",    "router", True),
    ("mesh node",       "router", True),
    ("wifi extender",   "router", True),
    ("range extender",  "router", True),
    ("eero",            "router", True),
    ("orbi",            "router", True),
    ("unifi",           "router", True),
    ("ubiquiti",        "router", True),
    ("mikrotik",        "router", True),
    ("gateway",         "router", False),
    ("deco",            "router", False),

    # ── SAR / emergency devices ───────────────────────────────────────────
    ("garmin inreach",  "sar_device", True),
    ("garmin montana",  "sar_device", True),
    ("garmin gpsmap",   "sar_device", True),
    ("garmin rino",     "sar_device", True),
    ("garmin rhino",    "sar_device", True),
    ("kenwood",         "sar_device", True),
    ("baofeng",         "sar_device", True),
    ("yaesu",           "sar_device", True),
    ("icom",            "sar_device", True),
    ("hytera",          "sar_device", True),
    ("sepura",          "sar_device", True),
    ("motorola solutions", "sar_device", True),
    ("recco",           "sar_device", True),
    ("sar beacon",      "sar_device", True),
    ("epirb",           "sar_device", True),
    ("flir",            "sar_device", True),
    ("thermal cam",     "sar_device", True),
    ("two-way radio",   "sar_device", True),
    ("2-way radio",     "sar_device", True),
    ("harris radio",    "sar_device", True),
    ("tait radio",      "sar_device", True),
    ("transceiver",     "sar_device", False),
    ("walkie",          "sar_device", False),
    ("plb",             "sar_device", False),
    ("gopro",           "sar_device", False),
    ("avalanche",       "sar_device", False),

    # ── IoT / smart home ──────────────────────────────────────────────────
    ("philips hue",     "iot", True),
    ("hue bridge",      "iot", True),
    ("lifx",            "iot", True),
    ("sonoff",          "iot", True),
    ("tuya",            "iot", True),
    ("smart plug",      "iot", True),
    ("smart bulb",      "iot", True),
    ("smart light",     "iot", True),
    ("smart lock",      "iot", True),
    ("smart sensor",    "iot", True),
    ("ecobee",          "iot", True),
    ("wyze",            "iot", True),
    ("arlo",            "iot", True),
    ("zigbee",          "iot", True),
    ("z-wave",          "iot", True),
    ("esp32",           "iot", True),
    ("esp8266",         "iot", True),
    ("arduino",         "iot", True),
    ("raspberry",       "iot", True),
    ("tasmota",         "iot", True),
    ("home assistant",  "iot", True),
    ("nest",            "iot", False),
    ("ring",            "iot", False),
    ("eufy",            "iot", False),
    ("blink",           "iot", False),
    ("homekit",         "iot", False),

    # ── Civil infrastructure ──────────────────────────────────────────────
    ("traffic light",   "civil_infrastructure", True),
    ("traffic signal",  "civil_infrastructure", True),
    ("traffic control", "civil_infrastructure", True),
    ("parking meter",   "civil_infrastructure", True),
    ("smart parking",   "civil_infrastructure", True),
    ("smart city",      "civil_infrastructure", True),
    ("street light",    "civil_infrastructure", True),
    ("streetlight",     "civil_infrastructure", True),
    ("utility meter",   "civil_infrastructure", True),
    ("smart meter",     "civil_infrastructure", True),
    ("water meter",     "civil_infrastructure", True),
    ("gas meter",       "civil_infrastructure", True),
    ("electric meter",  "civil_infrastructure", True),
    ("scada",           "civil_infrastructure", True),

    # ── Audio / speakers (not headphones) ─────────────────────────────────
    ("sonos",           "audio", True),
    ("homepod",         "audio", True),
    ("echo dot",        "audio", True),
    ("echo show",       "audio", True),
    ("amazon echo",     "audio", True),
    ("google home",     "audio", True),
    ("jbl charge",      "audio", True),
    ("jbl flip",        "audio", True),
    ("jbl xtreme",      "audio", True),
    ("jbl go ",         "audio", True),
    ("jbl clip",        "audio", True),
    ("bose soundlink",  "audio", True),
    ("bose portable",   "audio", True),
    ("beats pill",      "audio", True),
    ("soundbar",        "audio", True),
    ("subwoofer",       "audio", True),
    ("speaker",         "audio", False),
    ("marshall",        "audio", False),

    # ── Cameras ───────────────────────────────────────────────────────────
    ("camera",          "camera", False),

    # ── Printers ──────────────────────────────────────────────────────────
    ("printer",         "printer", True),
    ("canon pixma",     "printer", True),
    ("hp envy",         "printer", True),
    ("hp officejet",    "printer", True),
    ("brother hl",      "printer", True),
    ("brother mfc",     "printer", True),
    ("epson",           "printer", False),

    # ── Automotive ────────────────────────────────────────────────────────
    ("carplay",         "automotive", True),
    ("android auto",    "automotive", True),
    ("tesla",           "automotive", True),
    ("car kit",         "automotive", True),
    ("car stereo",      "automotive", True),
    ("ford sync",       "automotive", True),
    ("obd",             "automotive", False),
    ("dashcam",         "automotive", False),
    ("bmw",             "automotive", False),
    ("mercedes",        "automotive", False),
    ("audi",            "automotive", False),
    ("toyota",          "automotive", False),
    ("honda",           "automotive", False),
]


# ═══════════════════════════════════════════════════════════════════════════
# 3. Manufacturer / OUI vendor → device type  (weakest signal → always [heur])
# ═══════════════════════════════════════════════════════════════════════════
# Ordered list of (category, keywords).  More specific categories first so
# they win when a vendor could match multiple categories.
_VENDOR_HEURISTICS: list[tuple[str, list[str]]] = [
    # Very specific categories first
    ("medical", [
        "medtronic", "dexcom", "abbott", "omron", "masimo",
        "ge healthcare", "siemens health", "philips medical",
        "insulet", "tandem diabetes", "boston scientific",
        "biotronik", "livanova",
    ]),
    ("drone", [
        "dji", "parrot", "autel robotics", "skydio",
    ]),
    ("civil_infrastructure", [
        "schneider electric", "landis+gyr", "itron",
        "sensus", "kamstrup", "siemens ag",
    ]),
    ("sar_device", [
        "garmin", "kenwood", "icom", "yaesu",
        "hytera", "sepura", "tait",
        "vertex standard", "l3harris",
    ]),
    ("printer", [
        "brother", "canon", "epson", "hp inc", "hewlett packard",
        "kyocera", "lexmark", "xerox", "ricoh",
    ]),
    ("automotive", [
        "tesla", "continental", "harman", "denso",
    ]),
    # Broader categories
    ("home_appliance", [
        "irobot", "roborock", "dyson", "ecovacs",
        "electrolux", "whirlpool", "miele", "haier",
    ]),
    ("tv", [
        "roku", "lg display", "vizio",
    ]),
    ("wearable", [
        "fitbit", "polar electro", "suunto", "fossil",
        "huami", "coros", "whoop", "withings",
    ]),
    ("headphones", [
        "bose", "jabra", "beats", "jbl", "sennheiser",
        "bang & olufsen", "audio-technica", "plantronics",
        "gn audio", "skullcandy", "anker soundcore", "1more",
    ]),
    ("iot", [
        "espressif", "tuya", "ring", "nest",
        "ecobee", "philips lighting", "signify",
        "lifx", "sonoff", "wyze", "eufy", "arlo",
        "shenzhen", "telink",
    ]),
    ("router", [
        "cisco", "juniper", "aruba", "ubiquiti", "mikrotik",
        "ruckus", "extreme networks", "fortinet", "palo alto",
        "meraki", "arista", "d-link", "linksys", "zyxel",
        "netgear", "buffalo", "tp-link", "tenda", "draytek",
        "peplink", "cradlepoint", "cambium", "mimosa",
        "engenius", "ruijie", "h3c",
    ]),
    ("computer", [
        "dell", "lenovo", "acer", "asustek", "msi",
        "gigabyte", "intel corporate", "microsoft",
    ]),
    # Most generic – last resort
    ("phone", [
        "apple", "samsung", "huawei", "xiaomi", "oppo", "vivo",
        "realme", "oneplus", "zte", "alcatel", "htc",
        "sony mobile", "motorola mobility", "google",
        "honor", "nothing", "fairphone", "essential",
    ]),
]


# ═══════════════════════════════════════════════════════════════════════════
# 4. WiFi SSID patterns → device type
# ═══════════════════════════════════════════════════════════════════════════
# (substring, device_type, sure_if_beacon)
_SSID_RULES: list[tuple[str, str, bool]] = [
    # Drone hotspots
    ("dji-",        "drone", True),
    ("phantom-",    "drone", True),
    ("mavic-",      "drone", True),
    ("skydio-",     "drone", True),
    ("parrot-",     "drone", False),

    # Phone tethering hotspots
    ("iphone",      "phone", True),
    ("androidap",   "phone", True),
    ("galaxy",      "phone", False),
    ("pixel",       "phone", False),

    # Router / infrastructure SSIDs
    ("ubnt",        "router", True),
    ("unifi",       "router", True),
    ("meraki",      "router", True),
    ("mikrotik",    "router", True),

    # IoT
    ("tuya",        "iot", True),
    ("tasmota",     "iot", True),
    ("esp_",        "iot", True),

    # TV / streaming
    ("chromecast",  "tv", True),
    ("firetv",      "tv", True),
    ("fire-tv",     "tv", True),
    ("roku",        "tv", False),

    # Printers (WiFi Direct)
    ("direct-",     "printer", False),
    ("hp-",         "printer", False),
]


# ═══════════════════════════════════════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════════════════════════════════════

def _extract_short_uuid(uuid_str: str) -> str:
    """Extract 16-bit UUID hex from a BLE UUID string.

    Handles:
      "0000180d-0000-1000-8000-00805f9b34fb" → "180d"
      "180d"                                  → "180d"
      "0x180D"                                → "180d"
      Vendor-specific 128-bit UUIDs           → returned as-is (won't match lookup)
    """
    if not uuid_str:
        return ""
    uuid_str = uuid_str.strip().lower()

    # Full 128-bit standard BT UUID
    if len(uuid_str) == 36 and uuid_str[8] == '-':
        # Standard base UUID suffix → extract 16-bit part
        if uuid_str.endswith("-0000-1000-8000-00805f9b34fb"):
            return uuid_str[4:8]
        return uuid_str  # vendor-specific, return full

    # Short with 0x prefix
    if uuid_str.startswith("0x"):
        return uuid_str[2:].lower()

    return uuid_str


# ═══════════════════════════════════════════════════════════════════════════
# Main classifier
# ═══════════════════════════════════════════════════════════════════════════

def classify_device(
    name: Optional[str] = None,
    manufacturer: Optional[str] = None,
    service_uuids: Optional[List[str]] = None,
    oui_vendor: Optional[str] = None,
    ssids: Optional[List[str]] = None,
    is_beacon: Optional[bool] = None,
    is_randomized_mac: bool = False,
) -> str:
    """Classify a device into a category based on all available signals.

    Args:
        name:            BLE advertised name (best name from all sightings)
        manufacturer:    BLE manufacturer company name (from BT SIG company ID)
        service_uuids:   List of BLE GATT service UUIDs observed across sightings
        oui_vendor:      WiFi/BT OUI vendor name (from MAC prefix lookup)
        ssids:           List of WiFi SSIDs probed or broadcast by the device
        is_beacon:       True if WiFi beacon (AP), False if ProbeRequest, None if BT/unknown
        is_randomized_mac: True if MAC is locally-administered (randomized)

    Returns:
        Device type string.  Empty string if no classification possible.
        Suffix " [heur]" on heuristic guesses.
    """

    # ── 1. BLE Service UUID (strongest signal) ────────────────────────────
    if service_uuids:
        for uuid_raw in service_uuids:
            short = _extract_short_uuid(uuid_raw)
            if short in _SERVICE_UUID_TYPES:
                return _SERVICE_UUID_TYPES[short]

    # ── 2. Name-based matching ────────────────────────────────────────────
    search_parts = [p for p in (name, manufacturer, oui_vendor) if p]
    search_text = ' '.join(search_parts).lower()

    if search_text.strip():
        for keyword, dtype, is_sure in _NAME_RULES:
            if keyword.lower() in search_text:
                return dtype if is_sure else f"{dtype} [heur]"

    # ── 3. WiFi SSID-based matching (before beacon fallback) ──────────────
    #    Check SSIDs early so phone hotspots (beacon + SSID "iPhone")
    #    are not misclassified as routers.
    if ssids:
        for ssid in ssids:
            ssid_lower = ssid.lower()
            for prefix, dtype, sure_if_beacon in _SSID_RULES:
                if prefix.lower() in ssid_lower:
                    if is_beacon is True and sure_if_beacon:
                        return dtype          # beacon + specific SSID = sure
                    return f"{dtype} [heur]"

    # ── 4. WiFi beacon → router (generic fallback) ────────────────────────
    if is_beacon is True:
        if oui_vendor:
            vendor_lower = oui_vendor.lower()
            for vk in dict(_VENDOR_HEURISTICS).get("router", []):
                if vk in vendor_lower:
                    return "router"
        return "router [heur]"

    # ── 5. Vendor / manufacturer heuristic ────────────────────────────────
    if search_text.strip():
        for dtype, vendor_keywords in _VENDOR_HEURISTICS:
            for vk in vendor_keywords:
                if vk.lower() in search_text:
                    return f"{dtype} [heur]"

    # ── 6. Randomized MAC without other signals → likely phone ────────────
    if is_randomized_mac:
        return "phone [heur]"

    return ""
