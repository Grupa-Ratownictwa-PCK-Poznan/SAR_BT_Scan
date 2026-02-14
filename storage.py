# file: storage.py
import sqlite3
import time
import os
from contextlib import contextmanager

from settings import SD_STORAGE, DB_FILE, SCANNER_ID

DB_PATH = SD_STORAGE + DB_FILE  #"/var/lib/ble/ble_scanner.db"

# Check if the configured database exists; if not, try fallback paths for testing on macOS
if not os.path.exists(DB_PATH):
    if os.path.exists('/tmp/test_results.db'):
        DB_PATH = '/tmp/test_results.db'
    elif os.path.exists('./test_results.db'):
        DB_PATH = './test_results.db'

def init_db():
    print("Saving to DB on location: " + DB_PATH)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA temp_store=MEMORY;")

    # Devices table (one row per unique BT addr)
    con.execute("""
    CREATE TABLE IF NOT EXISTS devices (
        addr TEXT PRIMARY KEY,
        first_seen INTEGER NOT NULL,
        last_seen INTEGER NOT NULL,
        name TEXT,
        manufacturer_hex TEXT,
        manufacturer TEXT
    );
    """)

    # Sightings table (each individual observation)
    con.execute("""
    CREATE TABLE IF NOT EXISTS sightings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        addr TEXT NOT NULL,
        ts_unix INTEGER NOT NULL,         -- capture time (Unix epoch)
        ts_gps TEXT,                      -- raw GPS timestamp (UTC, ISO8601)
        lat REAL,
        lon REAL,
        alt REAL,
        gps_hdop REAL,                    -- precision: Horizontal Dilution of Precision
        rssi INTEGER,
        tx_power INTEGER,
        local_name TEXT,
        manufacturer TEXT,
        manufacturer_hex TEXT,
        service_uuid TEXT,
        scanner_name TEXT,
        adv_raw BLOB,
        FOREIGN KEY(addr) REFERENCES devices(addr)
    );
    """)

    con.execute("CREATE INDEX IF NOT EXISTS idx_sightings_ts ON sightings(ts_unix);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_sightings_addr_ts ON sightings(addr, ts_unix);")

    # WiFi devices table (one row per unique WiFi device MAC)
    con.execute("""
    CREATE TABLE IF NOT EXISTS wifi_devices (
        mac TEXT PRIMARY KEY,
        first_seen INTEGER NOT NULL,
        last_seen INTEGER NOT NULL,
        vendor TEXT
    );
    """)

    # WiFi associations table (association requests with SSIDs)
    con.execute("""
    CREATE TABLE IF NOT EXISTS wifi_associations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mac TEXT NOT NULL,
        ts_unix INTEGER NOT NULL,           -- capture time (Unix epoch)
        ts_gps TEXT,                        -- raw GPS timestamp (UTC, ISO8601)
        lat REAL,
        lon REAL,
        alt REAL,
        ssid TEXT NOT NULL,                 -- plaintext SSID from assoc request
        rssi INTEGER,                       -- signal strength
        scanner_name TEXT,
        FOREIGN KEY(mac) REFERENCES wifi_devices(mac)
    );
    """)

    con.execute("CREATE INDEX IF NOT EXISTS idx_wifi_assoc_ts ON wifi_associations(ts_unix);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_wifi_assoc_mac_ts ON wifi_associations(mac, ts_unix);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_wifi_assoc_ssid ON wifi_associations(ssid);")

    con.commit()
    con.close()

@contextmanager
def db():
    con = sqlite3.connect(DB_PATH, isolation_level=None)
    try:
        yield con
    finally:
        con.close()

def upsert_device(con, addr, name=None, manufacturer=None, man_hex=None, now=None):
    now = now or int(time.time())
    con.execute("BEGIN;")
    con.execute("""
        INSERT INTO devices(addr, first_seen, last_seen, name, manufacturer, manufacturer_hex)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(addr) DO UPDATE SET
          last_seen=excluded.last_seen,
          name=COALESCE(excluded.name, devices.name),
          manufacturer=COALESCE(excluded.manufacturer, devices.manufacturer);
    """, (addr, now, now, name, manufacturer, man_hex))
    con.execute("COMMIT;")

def add_sighting(con, addr, ts_unix=None,ts_gps=None, lat=None, lon=None, alt=None,
                 gps_hdop=None, rssi=None, tx_power=None, local_name=None,
                 manufacturer=None, manufacturer_hex=None, service_uuid=None,
                 adv_raw=None, scanner=None):
    con.execute("BEGIN;")
    con.execute("""
        INSERT INTO sightings(
            addr, ts_unix, ts_gps, lat, lon, alt, gps_hdop,
            rssi, tx_power, local_name, manufacturer, manufacturer_hex, service_uuid,scanner_name, adv_raw
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (addr, ts_unix, ts_gps, lat, lon, alt, gps_hdop,
          rssi, tx_power, local_name, manufacturer, manufacturer_hex, service_uuid, scanner, adv_raw))
    con.execute("COMMIT;")

def upsert_wifi_device(con, mac, vendor=None, now=None):
    """Register or update a WiFi device."""
    now = now or int(time.time())
    con.execute("BEGIN;")
    con.execute("""
        INSERT INTO wifi_devices(mac, first_seen, last_seen, vendor)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(mac) DO UPDATE SET
          last_seen=excluded.last_seen,
          vendor=COALESCE(excluded.vendor, wifi_devices.vendor);
    """, (mac, now, now, vendor))
    con.execute("COMMIT;")

def add_wifi_association(con, mac, ssid, ts_unix=None, ts_gps=None, lat=None, lon=None, 
                         alt=None, rssi=None, scanner=None):
    """Record a WiFi association request (device trying to connect to SSID)."""
    con.execute("BEGIN;")
    con.execute("""
        INSERT INTO wifi_associations(
            mac, ts_unix, ts_gps, lat, lon, alt, ssid, rssi, scanner_name
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (mac, ts_unix, ts_gps, lat, lon, alt, ssid, rssi, scanner))
    con.execute("COMMIT;")
