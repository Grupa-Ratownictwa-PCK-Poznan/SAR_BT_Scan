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
        manufacturer TEXT,
        confidence INTEGER DEFAULT 0,
        notes TEXT DEFAULT ''
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
        vendor TEXT,
        device_type TEXT DEFAULT '',
        confidence INTEGER DEFAULT 0,
        notes TEXT DEFAULT ''
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

    # Migration: add new columns to existing tables if they don't exist
    _migrate_add_columns(con)

    con.commit()
    con.close()


def _migrate_add_columns(con):
    """Add new columns to existing tables for backward compatibility."""
    # Get existing columns for devices table
    cursor = con.execute("PRAGMA table_info(devices)")
    device_columns = {row[1] for row in cursor.fetchall()}
    
    # Add 'notes' column to devices if missing
    if 'notes' not in device_columns:
        try:
            con.execute("ALTER TABLE devices ADD COLUMN notes TEXT DEFAULT ''")
            print("Migration: Added 'notes' column to devices table")
        except sqlite3.OperationalError:
            pass  # Column might already exist
    
    # Get existing columns for wifi_devices table
    cursor = con.execute("PRAGMA table_info(wifi_devices)")
    wifi_columns = {row[1] for row in cursor.fetchall()}
    
    # Add 'device_type' column to wifi_devices if missing
    if 'device_type' not in wifi_columns:
        try:
            con.execute("ALTER TABLE wifi_devices ADD COLUMN device_type TEXT DEFAULT ''")
            print("Migration: Added 'device_type' column to wifi_devices table")
        except sqlite3.OperationalError:
            pass
    
    # Add 'notes' column to wifi_devices if missing
    if 'notes' not in wifi_columns:
        try:
            con.execute("ALTER TABLE wifi_devices ADD COLUMN notes TEXT DEFAULT ''")
            print("Migration: Added 'notes' column to wifi_devices table")
        except sqlite3.OperationalError:
            pass

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


def update_wifi_device_enrichment(con, mac, vendor=None, device_type=None, notes=None):
    """Update WiFi device with enrichment data (vendor lookup, device type guess, analyst notes).
    
    Only updates fields that are provided (not None). Empty strings will overwrite existing values.
    This function is called by the confidence analyzer to enrich WiFi devices.
    """
    updates = []
    params = []
    
    if vendor is not None:
        updates.append("vendor = ?")
        params.append(vendor)
    
    if device_type is not None:
        updates.append("device_type = ?")
        params.append(device_type)
    
    if notes is not None:
        updates.append("notes = ?")
        params.append(notes)
    
    if not updates:
        return
    
    params.append(mac)
    query = f"UPDATE wifi_devices SET {', '.join(updates)} WHERE mac = ?"
    
    con.execute("BEGIN;")
    con.execute(query, params)
    con.execute("COMMIT;")


def update_bt_device_notes(con, addr, notes):
    """Update Bluetooth device notes field.
    
    This allows analysts to add notes to BT devices.
    """
    con.execute("BEGIN;")
    con.execute("UPDATE devices SET notes = ? WHERE addr = ?", (notes, addr))
    con.execute("COMMIT;")


def get_wifi_device(con, mac):
    """Get a single WiFi device by MAC address."""
    cursor = con.execute(
        "SELECT mac, first_seen, last_seen, vendor, device_type, confidence, notes FROM wifi_devices WHERE mac = ?",
        (mac,)
    )
    row = cursor.fetchone()
    if row:
        return {
            "mac": row[0],
            "first_seen": row[1],
            "last_seen": row[2],
            "vendor": row[3] or "",
            "device_type": row[4] or "",
            "confidence": row[5],
            "notes": row[6] or ""
        }
    return None


def get_bt_device(con, addr):
    """Get a single Bluetooth device by address."""
    cursor = con.execute(
        "SELECT addr, first_seen, last_seen, name, manufacturer_hex, manufacturer, confidence, notes FROM devices WHERE addr = ?",
        (addr,)
    )
    row = cursor.fetchone()
    if row:
        return {
            "addr": row[0],
            "first_seen": row[1],
            "last_seen": row[2],
            "name": row[3] or "",
            "manufacturer_hex": row[4] or "",
            "manufacturer": row[5] or "",
            "confidence": row[6],
            "notes": row[7] or ""
        }
    return None
