# file: storage.py
import sqlite3
import time
from contextlib import contextmanager

from settings import SD_STORAGE, DB_FILE, SCANNER_ID

DB_PATH = SD_STORAGE + DB_FILE  #"/var/lib/ble/ble_scanner.db"

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
