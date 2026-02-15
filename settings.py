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