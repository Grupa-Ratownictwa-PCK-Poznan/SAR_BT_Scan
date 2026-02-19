#!/usr/bin/env python3
"""Create test database with sample GPS sightings for heatmap testing."""

import sqlite3
import time

# Create a test database - same location as production on macOS
db_path = '/tmp/test_results.db'
con = sqlite3.connect(db_path)

# Create tables matching storage.py schema
con.execute("""
CREATE TABLE IF NOT EXISTS devices (
    addr TEXT PRIMARY KEY,
    first_seen INTEGER NOT NULL,
    last_seen INTEGER NOT NULL,
    name TEXT,
    manufacturer_hex TEXT,
    manufacturer TEXT,
    confidence INTEGER DEFAULT 0,
    notes TEXT DEFAULT ''
)
""")

con.execute("""
CREATE TABLE IF NOT EXISTS sightings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    addr TEXT NOT NULL,
    ts_unix INTEGER NOT NULL,
    ts_gps TEXT,
    lat REAL,
    lon REAL,
    alt REAL,
    gps_hdop REAL,
    rssi INTEGER,
    tx_power INTEGER,
    local_name TEXT,
    manufacturer TEXT,
    manufacturer_hex TEXT,
    service_uuid TEXT,
    scanner_name TEXT,
    adv_raw BLOB,
    FOREIGN KEY(addr) REFERENCES devices(addr)
)
""")

con.execute("""
CREATE TABLE IF NOT EXISTS wifi_devices (
    mac TEXT PRIMARY KEY,
    first_seen INTEGER NOT NULL,
    last_seen INTEGER NOT NULL,
    vendor TEXT,
    device_type TEXT DEFAULT '',
    confidence INTEGER DEFAULT 0,
    notes TEXT DEFAULT ''
)
""")

con.execute("""
CREATE TABLE IF NOT EXISTS wifi_associations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac TEXT,
    ts_unix INTEGER NOT NULL,
    ts_gps TEXT,
    lat REAL,
    lon REAL,
    alt REAL,
    ssid TEXT,
    packet_type TEXT DEFAULT 'ProbeRequest',
    rssi INTEGER,
    scanner_name TEXT
)
""")

# Insert sample BT devices
devices = [
    ('AA:BB:CC:DD:EE:01', 'Device 1'),
    ('AA:BB:CC:DD:EE:02', 'Device 2'),
    ('AA:BB:CC:DD:EE:03', 'Device 3'),
]
now = int(time.time())
for mac, name in devices:
    con.execute(
        'INSERT OR IGNORE INTO devices (addr, first_seen, last_seen, name, manufacturer, manufacturer_hex) VALUES (?, ?, ?, ?, ?, ?)',
        (mac, now - 1000, now, name, 'Test', '0x0001')
    )

# Insert sample GPS sightings with coordinates
sightings = [
    ('AA:BB:CC:DD:EE:01', now - 100, 51.505, -0.09, -50),     # London
    ('AA:BB:CC:DD:EE:02', now - 200, 51.50, -0.095, -60),      # Near London
    ('AA:BB:CC:DD:EE:03', now - 300, 51.51, -0.085, -45),      # North London
    ('AA:BB:CC:DD:EE:01', now - 400, 51.506, -0.091, -55),     # London variant
    ('AA:BB:CC:DD:EE:02', now - 500, 48.8566, 2.3522, -70),    # Paris
    ('AA:BB:CC:DD:EE:03', now - 600, 48.85, 2.35, -55),        # Near Paris
]
for addr, ts, lat, lon, rssi in sightings:
    con.execute(
        'INSERT INTO sightings (addr, ts_unix, lat, lon, rssi) VALUES (?, ?, ?, ?, ?)',
        (addr, ts, lat, lon, rssi)
    )

# Insert sample WiFi data
con.execute(
    'INSERT OR IGNORE INTO wifi_devices (mac, first_seen, last_seen, vendor, device_type) VALUES (?, ?, ?, ?, ?)',
    ('11:22:33:44:55:01', now - 1000, now, 'Apple, Inc.', 'phone')
)

con.commit()
con.close()

print(f'✓ Test database created at {db_path}')
print('✓ Added 6 GPS sightings with coordinates (London and Paris)')
print('✓ Run: export SD_STORAGE=/tmp/  && python web_ui/app.py')
