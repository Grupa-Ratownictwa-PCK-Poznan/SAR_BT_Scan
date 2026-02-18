USB_STORAGE = "/mnt/pendrive"
SD_STORAGE = "/home/grpck/"
DB_FILE = "results.db"

BLEAK_DEVICE = "hci1"

SCANNER_ID = "Scanner 1"

# WiFi scanning configuration
SCAN_MODE = "both"  # Options: "bt", "wifi", or "both"
WIFI_INTERFACE = "wlan1"  # USB WiFi adapter interface in monitor mode
KNOWN_WIFIS = []  # List of known SSIDs to identify (empty = capture all)

# Database configuration
CLEAN_DB_ON_STARTUP = False  # Set to True to delete database file on each supervisor start

# Web UI configuration
WEB_UI_ENABLED = True  # Set to False to disable web interface
WEB_UI_HOST = "0.0.0.0"  # Listen on all interfaces
WEB_UI_PORT = 8000  # Local port for web UI
WEB_UI_REFRESH_INTERVAL = 1.0  # Seconds between live updates (WebSocket)

# Confidence Analyzer configuration
# HQ/base location for GPS clustering analysis (set to your staging area coordinates)
# If set to (None, None), the analyzer will auto-detect HQ from first session sighting
HQ_LATITUDE = None   # e.g., 30.2297
HQ_LONGITUDE = None  # e.g., 10.0122
HQ_RADIUS_METERS = 100  # Devices seen only within this radius of HQ get lower confidence

# Path to device whitelist file (team equipment MACs)
DEVICE_WHITELIST_FILE = "device_whitelist.txt"

# Multi-session detection: minimum gap (seconds) between sightings to start new session
SESSION_GAP_SECONDS = 7200  # 2 hours = new session boundary