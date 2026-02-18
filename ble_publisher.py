#!/usr/bin/env python3
"""
BLE GATT Publisher for SAR Scanner.

Publishes scanner sightings (Bluetooth and WiFi) over BLE GATT to a companion app.
Uses the built-in Bluetooth interface (hci0) to avoid interfering with the scanner (hci1).

This module is completely decoupled from the scanner - it only reads from the SQLite
database via polling. No modifications to scanner code required.

Requires:
  - BlueZ 5.50+ (comes with most Linux distros)
  - Python packages: dbus-python, PyGObject
  - Run as root or add user to 'bluetooth' group

Usage:
  from ble_publisher import BLEGATTPublisher
  publisher = BLEGATTPublisher()
  publisher.run()  # Blocking, run in a thread
"""

import os
import sys
import time
import sqlite3
import threading
import signal
import struct
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass
from queue import Queue, Empty

# Protocol definitions
from ble_protocol import (
    SERVICE_UUID,
    CHAR_LIVE_FEED_UUID,
    CHAR_CONTROL_UUID,
    CHAR_STATUS_UUID,
    CHAR_BULK_TRANSFER_UUID,
    PROTOCOL_VERSION,
    SightingType,
    ControlCommand,
    GPSFixStatus,
    BTSighting,
    WiFiSighting,
    ScannerStatus,
    BulkRequest,
    BulkChunk,
    encode_bt_sighting,
    encode_wifi_sighting,
    encode_status,
    decode_control_command,
    decode_bulk_request,
    encode_bulk_chunk,
    encode_advertising_manufacturer_data,
)

# Settings import
try:
    from settings import (
        BLE_PUBLISH_ENABLED,
        BLE_PUBLISH_INTERFACE,
        BLE_PUBLISH_DEVICE_NAME,
        BLE_PUBLISH_POLL_INTERVAL,
        BLE_PUBLISH_AGGREGATION_MS,
        BLE_PUBLISH_MIN_RSSI,
        SCANNER_ID,
    )
except ImportError:
    # Defaults if settings not configured
    BLE_PUBLISH_ENABLED = False
    BLE_PUBLISH_INTERFACE = "hci0"
    BLE_PUBLISH_DEVICE_NAME = "SAR-Scanner"
    BLE_PUBLISH_POLL_INTERVAL = 0.5
    BLE_PUBLISH_AGGREGATION_MS = 200
    BLE_PUBLISH_MIN_RSSI = -100
    SCANNER_ID = "Scanner"

# Version
__version__ = "1.0.0"

# Try to import BlueZ D-Bus bindings
BLUEZ_AVAILABLE = False
try:
    import dbus
    import dbus.exceptions
    import dbus.mainloop.glib
    import dbus.service
    from gi.repository import GLib
    BLUEZ_AVAILABLE = True
except ImportError as e:
    print(f"Warning: BlueZ D-Bus bindings not available: {e}")
    print("Install with: sudo apt install python3-dbus python3-gi")


# ============================================================================
# BlueZ D-Bus Constants
# ============================================================================

BLUEZ_SERVICE_NAME = "org.bluez"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
GATT_DESC_IFACE = "org.bluez.GattDescriptor1"
LE_ADVERTISING_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
LE_ADVERTISEMENT_IFACE = "org.bluez.LEAdvertisement1"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP_IFACE = "org.freedesktop.DBus.Properties"


# ============================================================================
# Database Interface (Read-only, polling)
# ============================================================================

class SightingPoller:
    """
    Polls the SQLite database for new sightings.
    Completely independent of the scanner - only reads from the database.
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.last_bt_id = 0
        self.last_wifi_id = 0
        self._determine_initial_ids()
    
    def _determine_initial_ids(self):
        """Get the current max IDs to start polling from current point."""
        try:
            con = sqlite3.connect(self.db_path, timeout=5.0)
            con.row_factory = sqlite3.Row
            
            # Get max BT sighting ID
            row = con.execute("SELECT MAX(id) as max_id FROM sightings").fetchone()
            if row and row["max_id"]:
                self.last_bt_id = row["max_id"]
            
            # Get max WiFi sighting ID
            row = con.execute("SELECT MAX(id) as max_id FROM wifi_associations").fetchone()
            if row and row["max_id"]:
                self.last_wifi_id = row["max_id"]
            
            con.close()
        except Exception as e:
            print(f"[BLE Publisher] DB init warning: {e}")
    
    def poll_bt_sightings(self, min_rssi: int = -100, limit: int = 50) -> List[BTSighting]:
        """Poll for new Bluetooth sightings since last poll."""
        sightings = []
        try:
            con = sqlite3.connect(self.db_path, timeout=5.0)
            con.row_factory = sqlite3.Row
            
            rows = con.execute("""
                SELECT id, addr, ts_unix, ts_gps, lat, lon, rssi, 
                       tx_power, local_name, manufacturer, manufacturer_hex
                FROM sightings 
                WHERE id > ? AND (rssi IS NULL OR rssi >= ?)
                ORDER BY id 
                LIMIT ?
            """, (self.last_bt_id, min_rssi, limit)).fetchall()
            
            for row in rows:
                self.last_bt_id = row["id"]
                sightings.append(BTSighting(
                    addr=row["addr"],
                    ts_unix=row["ts_unix"] or 0,
                    ts_gps=row["ts_gps"],
                    lat=row["lat"],
                    lon=row["lon"],
                    rssi=row["rssi"],
                    local_name=row["local_name"],
                    manufacturer=row["manufacturer"],
                    manufacturer_hex=row["manufacturer_hex"],
                    tx_power=row["tx_power"]
                ))
            
            con.close()
        except Exception as e:
            print(f"[BLE Publisher] BT poll error: {e}")
        
        return sightings
    
    def poll_wifi_sightings(self, min_rssi: int = -100, limit: int = 50) -> List[WiFiSighting]:
        """Poll for new WiFi sightings since last poll."""
        sightings = []
        try:
            con = sqlite3.connect(self.db_path, timeout=5.0)
            con.row_factory = sqlite3.Row
            
            rows = con.execute("""
                SELECT id, mac, ts_unix, ts_gps, lat, lon, ssid, rssi
                FROM wifi_associations 
                WHERE id > ? AND (rssi IS NULL OR rssi >= ?)
                ORDER BY id 
                LIMIT ?
            """, (self.last_wifi_id, min_rssi, limit)).fetchall()
            
            for row in rows:
                self.last_wifi_id = row["id"]
                sightings.append(WiFiSighting(
                    mac=row["mac"],
                    ts_unix=row["ts_unix"] or 0,
                    ts_gps=row["ts_gps"],
                    lat=row["lat"],
                    lon=row["lon"],
                    ssid=row["ssid"] or "",
                    rssi=row["rssi"]
                ))
            
            con.close()
        except Exception as e:
            print(f"[BLE Publisher] WiFi poll error: {e}")
        
        return sightings
    
    def get_counts(self) -> tuple:
        """Get total sighting counts from database."""
        bt_count = 0
        wifi_count = 0
        try:
            con = sqlite3.connect(self.db_path, timeout=5.0)
            
            row = con.execute("SELECT COUNT(*) as cnt FROM sightings").fetchone()
            if row:
                bt_count = row[0]
            
            row = con.execute("SELECT COUNT(*) as cnt FROM wifi_associations").fetchone()
            if row:
                wifi_count = row[0]
            
            con.close()
        except Exception:
            pass
        
        return bt_count, wifi_count
    
    def get_bulk_sightings(self, ts_start: int, ts_end: int, 
                           sighting_type: int = 0) -> List[bytes]:
        """
        Get sightings in a time range for bulk transfer.
        Returns list of encoded sighting packets.
        """
        packets = []
        seq = 0
        
        try:
            con = sqlite3.connect(self.db_path, timeout=10.0)
            con.row_factory = sqlite3.Row
            
            # BT sightings
            if sighting_type in (0, 1):
                rows = con.execute("""
                    SELECT addr, ts_unix, ts_gps, lat, lon, rssi, 
                           tx_power, local_name, manufacturer, manufacturer_hex
                    FROM sightings 
                    WHERE ts_unix >= ? AND ts_unix <= ?
                    ORDER BY ts_unix
                """, (ts_start, ts_end)).fetchall()
                
                for row in rows:
                    sighting = BTSighting(
                        addr=row["addr"],
                        ts_unix=row["ts_unix"] or 0,
                        ts_gps=row["ts_gps"],
                        lat=row["lat"],
                        lon=row["lon"],
                        rssi=row["rssi"],
                        local_name=row["local_name"],
                        manufacturer=row["manufacturer"],
                        manufacturer_hex=row["manufacturer_hex"],
                        tx_power=row["tx_power"]
                    )
                    packets.append(encode_bt_sighting(sighting, seq))
                    seq += 1
            
            # WiFi sightings
            if sighting_type in (0, 2):
                rows = con.execute("""
                    SELECT mac, ts_unix, ts_gps, lat, lon, ssid, rssi
                    FROM wifi_associations 
                    WHERE ts_unix >= ? AND ts_unix <= ?
                    ORDER BY ts_unix
                """, (ts_start, ts_end)).fetchall()
                
                for row in rows:
                    sighting = WiFiSighting(
                        mac=row["mac"],
                        ts_unix=row["ts_unix"] or 0,
                        ts_gps=row["ts_gps"],
                        lat=row["lat"],
                        lon=row["lon"],
                        ssid=row["ssid"] or "",
                        rssi=row["rssi"]
                    )
                    packets.append(encode_wifi_sighting(sighting, seq))
                    seq += 1
            
            con.close()
        except Exception as e:
            print(f"[BLE Publisher] Bulk query error: {e}")
        
        return packets


# ============================================================================
# BlueZ D-Bus GATT Implementation
# ============================================================================

if BLUEZ_AVAILABLE:
    
    class Advertisement(dbus.service.Object):
        """BLE Advertisement for scanner discovery."""
        
        PATH_BASE = "/org/bluez/sar_scanner/advertisement"
        
        def __init__(self, bus, index, device_name: str, manufacturer_data: bytes):
            self.path = f"{self.PATH_BASE}{index}"
            self.bus = bus
            self.device_name = device_name
            self.manufacturer_data = manufacturer_data
            self._service_uuids = [SERVICE_UUID]
            dbus.service.Object.__init__(self, bus, self.path)
        
        def get_properties(self) -> dict:
            properties = {
                LE_ADVERTISEMENT_IFACE: {
                    "Type": "peripheral",
                    "LocalName": dbus.String(self.device_name),
                    "ServiceUUIDs": dbus.Array(self._service_uuids, signature="s"),
                    "ManufacturerData": dbus.Dictionary(
                        {0xFFFF: dbus.Array(self.manufacturer_data, signature="y")},
                        signature="qv"
                    ),
                    "Includes": dbus.Array(["tx-power"], signature="s"),
                }
            }
            return properties
        
        def update_manufacturer_data(self, data: bytes):
            """Update manufacturer data (for live status updates)."""
            self.manufacturer_data = data
        
        @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
        def GetAll(self, interface):
            if interface != LE_ADVERTISEMENT_IFACE:
                raise dbus.exceptions.DBusException(
                    "org.freedesktop.DBus.Error.InvalidArgs",
                    f"Unknown interface: {interface}"
                )
            return self.get_properties()[LE_ADVERTISEMENT_IFACE]
        
        @dbus.service.method(LE_ADVERTISEMENT_IFACE, in_signature="", out_signature="")
        def Release(self):
            print(f"[BLE Publisher] Advertisement released: {self.path}")
    
    
    class Characteristic(dbus.service.Object):
        """Base GATT Characteristic."""
        
        def __init__(self, bus, index, uuid, flags, service):
            self.path = f"{service.path}/char{index}"
            self.bus = bus
            self.uuid = uuid
            self.flags = flags
            self.service = service
            self.notifying = False
            self._value = []
            dbus.service.Object.__init__(self, bus, self.path)
        
        def get_properties(self) -> dict:
            return {
                GATT_CHRC_IFACE: {
                    "Service": self.service.get_path(),
                    "UUID": self.uuid,
                    "Flags": self.flags,
                    "Notifying": self.notifying,
                }
            }
        
        def get_path(self):
            return dbus.ObjectPath(self.path)
        
        @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
        def GetAll(self, interface):
            if interface != GATT_CHRC_IFACE:
                raise dbus.exceptions.DBusException(
                    "org.freedesktop.DBus.Error.InvalidArgs",
                    f"Unknown interface: {interface}"
                )
            return self.get_properties()[GATT_CHRC_IFACE]
        
        @dbus.service.method(GATT_CHRC_IFACE, in_signature="a{sv}", out_signature="ay")
        def ReadValue(self, options):
            return self._value
        
        @dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}", out_signature="")
        def WriteValue(self, value, options):
            pass
        
        @dbus.service.method(GATT_CHRC_IFACE)
        def StartNotify(self):
            if self.notifying:
                return
            self.notifying = True
        
        @dbus.service.method(GATT_CHRC_IFACE)
        def StopNotify(self):
            self.notifying = False
        
        @dbus.service.signal(DBUS_PROP_IFACE, signature="sa{sv}as")
        def PropertiesChanged(self, interface, changed, invalidated):
            pass
        
        def send_notification(self, value: bytes):
            """Send a notification/indication to subscribed clients."""
            if not self.notifying:
                return
            self._value = dbus.Array(value, signature="y")
            self.PropertiesChanged(GATT_CHRC_IFACE, {"Value": self._value}, [])
    
    
    class LiveFeedCharacteristic(Characteristic):
        """Live sighting feed characteristic (Notify)."""
        
        def __init__(self, bus, index, service, publisher):
            super().__init__(
                bus, index, CHAR_LIVE_FEED_UUID, ["notify"], service
            )
            self.publisher = publisher
        
        def StartNotify(self):
            super().StartNotify()
            print("[BLE Publisher] LiveFeed: Client subscribed")
            self.publisher.on_live_feed_subscribe()
        
        def StopNotify(self):
            super().StopNotify()
            print("[BLE Publisher] LiveFeed: Client unsubscribed")
            self.publisher.on_live_feed_unsubscribe()
    
    
    class ControlCharacteristic(Characteristic):
        """Control characteristic (Write)."""
        
        def __init__(self, bus, index, service, publisher):
            super().__init__(
                bus, index, CHAR_CONTROL_UUID, ["write", "write-without-response"], service
            )
            self.publisher = publisher
        
        @dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}", out_signature="")
        def WriteValue(self, value, options):
            data = bytes(value)
            self.publisher.on_control_write(data)
    
    
    class StatusCharacteristic(Characteristic):
        """Status characteristic (Read, Notify)."""
        
        def __init__(self, bus, index, service, publisher):
            super().__init__(
                bus, index, CHAR_STATUS_UUID, ["read", "notify"], service
            )
            self.publisher = publisher
        
        @dbus.service.method(GATT_CHRC_IFACE, in_signature="a{sv}", out_signature="ay")
        def ReadValue(self, options):
            status_bytes = self.publisher.get_status_bytes()
            return dbus.Array(status_bytes, signature="y")
    
    
    class BulkTransferCharacteristic(Characteristic):
        """Bulk transfer characteristic (Notify, Write)."""
        
        def __init__(self, bus, index, service, publisher):
            super().__init__(
                bus, index, CHAR_BULK_TRANSFER_UUID, ["notify", "write"], service
            )
            self.publisher = publisher
        
        @dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}", out_signature="")
        def WriteValue(self, value, options):
            data = bytes(value)
            self.publisher.on_bulk_request(data, self)
    
    
    class SARScannerService(dbus.service.Object):
        """SAR Scanner GATT Service."""
        
        PATH_BASE = "/org/bluez/sar_scanner/service"
        
        def __init__(self, bus, index, publisher):
            self.path = f"{self.PATH_BASE}{index}"
            self.bus = bus
            self.uuid = SERVICE_UUID
            self.primary = True
            self.characteristics = []
            dbus.service.Object.__init__(self, bus, self.path)
            
            # Create characteristics
            self.live_feed_char = LiveFeedCharacteristic(bus, 0, self, publisher)
            self.control_char = ControlCharacteristic(bus, 1, self, publisher)
            self.status_char = StatusCharacteristic(bus, 2, self, publisher)
            self.bulk_char = BulkTransferCharacteristic(bus, 3, self, publisher)
            
            self.characteristics = [
                self.live_feed_char,
                self.control_char,
                self.status_char,
                self.bulk_char
            ]
        
        def get_properties(self) -> dict:
            return {
                GATT_SERVICE_IFACE: {
                    "UUID": self.uuid,
                    "Primary": self.primary,
                    "Characteristics": dbus.Array(
                        [c.get_path() for c in self.characteristics],
                        signature="o"
                    )
                }
            }
        
        def get_path(self):
            return dbus.ObjectPath(self.path)
        
        @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
        def GetAll(self, interface):
            if interface != GATT_SERVICE_IFACE:
                raise dbus.exceptions.DBusException(
                    "org.freedesktop.DBus.Error.InvalidArgs",
                    f"Unknown interface: {interface}"
                )
            return self.get_properties()[GATT_SERVICE_IFACE]
        
        def get_characteristic_paths(self):
            return [c.path for c in self.characteristics]
    
    
    class Application(dbus.service.Object):
        """GATT Application containing all services."""
        
        def __init__(self, bus, publisher):
            self.path = "/org/bluez/sar_scanner"
            self.services = []
            dbus.service.Object.__init__(self, bus, self.path)
            
            # Create the SAR Scanner service
            self.service = SARScannerService(bus, 0, publisher)
            self.services.append(self.service)
        
        def get_path(self):
            return dbus.ObjectPath(self.path)
        
        @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
        def GetManagedObjects(self):
            response = {}
            
            for service in self.services:
                response[service.get_path()] = service.get_properties()
                for char in service.characteristics:
                    response[char.get_path()] = char.get_properties()
            
            return response


# ============================================================================
# Main BLE GATT Publisher Class
# ============================================================================

class BLEGATTPublisher:
    """
    BLE GATT Server for publishing scanner sightings to a companion app.
    
    Uses the built-in Bluetooth interface (hci0) to avoid interfering with
    the scanner which uses hci1. Polls the SQLite database for new sightings
    and pushes them to connected clients via GATT notifications.
    
    Usage:
        publisher = BLEGATTPublisher(db_path="/path/to/results.db")
        publisher.run()  # Blocking - run in a thread
    """
    
    def __init__(
        self,
        db_path: Optional[str] = None,
        interface: str = BLE_PUBLISH_INTERFACE,
        device_name: str = BLE_PUBLISH_DEVICE_NAME,
        poll_interval: float = BLE_PUBLISH_POLL_INTERVAL,
        aggregation_ms: int = BLE_PUBLISH_AGGREGATION_MS,
        min_rssi: int = BLE_PUBLISH_MIN_RSSI
    ):
        self.interface = interface
        self.device_name = device_name
        self.poll_interval = poll_interval
        self.aggregation_ms = aggregation_ms
        self.min_rssi = min_rssi
        
        # Determine database path
        if db_path:
            self.db_path = db_path
        else:
            # Try to import from storage module
            try:
                from storage import DB_PATH
                self.db_path = DB_PATH
            except ImportError:
                # Fallback paths
                for path in ["/home/grpck/results.db", "/tmp/test_results.db", "./results.db"]:
                    if os.path.exists(path):
                        self.db_path = path
                        break
                else:
                    self.db_path = "./results.db"
        
        # State
        self._running = False
        self._paused = False
        self._subscribers = 0
        self._seq_num = 0
        self._queue: Queue = Queue(maxsize=1000)
        
        # Statistics
        self._bt_sent = 0
        self._wifi_sent = 0
        
        # D-Bus / BlueZ objects
        self._bus = None
        self._mainloop = None
        self._application = None
        self._advertisement = None
        self._service = None
        self._adapter_path = None
        
        # Database poller
        self._poller: Optional[SightingPoller] = None
        
        print(f"[BLE Publisher] Initialized")
        print(f"  Interface: {self.interface}")
        print(f"  Device name: {self.device_name}")
        print(f"  Database: {self.db_path}")
        print(f"  Poll interval: {self.poll_interval}s")
        print(f"  Min RSSI filter: {self.min_rssi} dBm")
    
    def run(self):
        """
        Main run loop (blocking).
        Call this from a background thread.
        """
        if not BLUEZ_AVAILABLE:
            print("[BLE Publisher] ERROR: BlueZ D-Bus bindings not available")
            print("  Install with: sudo apt install python3-dbus python3-gi")
            return
        
        self._running = True
        
        try:
            # Initialize D-Bus
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            self._bus = dbus.SystemBus()
            
            # Find the Bluetooth adapter
            self._adapter_path = self._find_adapter()
            if not self._adapter_path:
                print(f"[BLE Publisher] ERROR: Bluetooth adapter {self.interface} not found")
                return
            
            print(f"[BLE Publisher] Using adapter: {self._adapter_path}")
            
            # Power on the adapter if needed
            self._power_on_adapter()
            
            # Initialize database poller
            self._poller = SightingPoller(self.db_path)
            
            # Create GATT application
            self._application = Application(self._bus, self)
            self._service = self._application.service
            
            # Register GATT application
            self._register_gatt_application()
            
            # Create and register advertisement
            mfr_data = self._get_advertising_data()
            self._advertisement = Advertisement(
                self._bus, 0, self.device_name, mfr_data
            )
            self._register_advertisement()
            
            # Start polling thread
            poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
            poll_thread.start()
            
            # Run the GLib main loop
            print("[BLE Publisher] GATT server started, waiting for connections...")
            self._mainloop = GLib.MainLoop()
            self._mainloop.run()
            
        except Exception as e:
            print(f"[BLE Publisher] ERROR: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._running = False
            self._cleanup()
    
    def stop(self):
        """Stop the publisher."""
        self._running = False
        if self._mainloop:
            self._mainloop.quit()
    
    def _find_adapter(self) -> Optional[str]:
        """Find the BlueZ adapter object path for our interface."""
        try:
            obj_manager = dbus.Interface(
                self._bus.get_object(BLUEZ_SERVICE_NAME, "/"),
                DBUS_OM_IFACE
            )
            objects = obj_manager.GetManagedObjects()
            
            for path, interfaces in objects.items():
                if "org.bluez.Adapter1" in interfaces:
                    # Check if this is our interface
                    props = interfaces["org.bluez.Adapter1"]
                    # The adapter name is typically hciX
                    if path.endswith(self.interface) or self.interface in str(path):
                        return path
            
            # If specific interface not found, return first adapter
            for path, interfaces in objects.items():
                if "org.bluez.Adapter1" in interfaces:
                    return path
            
        except Exception as e:
            print(f"[BLE Publisher] Error finding adapter: {e}")
        
        return None
    
    def _power_on_adapter(self):
        """Ensure the Bluetooth adapter is powered on."""
        try:
            adapter = dbus.Interface(
                self._bus.get_object(BLUEZ_SERVICE_NAME, self._adapter_path),
                DBUS_PROP_IFACE
            )
            powered = adapter.Get("org.bluez.Adapter1", "Powered")
            if not powered:
                print("[BLE Publisher] Powering on Bluetooth adapter...")
                adapter.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(True))
                time.sleep(1)
        except Exception as e:
            print(f"[BLE Publisher] Warning: Could not check/set adapter power: {e}")
    
    def _register_gatt_application(self):
        """Register the GATT application with BlueZ."""
        try:
            gatt_manager = dbus.Interface(
                self._bus.get_object(BLUEZ_SERVICE_NAME, self._adapter_path),
                GATT_MANAGER_IFACE
            )
            gatt_manager.RegisterApplication(
                self._application.get_path(),
                {},
                reply_handler=self._register_app_callback,
                error_handler=self._register_app_error
            )
        except Exception as e:
            print(f"[BLE Publisher] Error registering GATT application: {e}")
            raise
    
    def _register_app_callback(self):
        print("[BLE Publisher] GATT application registered successfully")
    
    def _register_app_error(self, error):
        print(f"[BLE Publisher] Failed to register GATT application: {error}")
    
    def _register_advertisement(self):
        """Register the BLE advertisement with BlueZ."""
        try:
            ad_manager = dbus.Interface(
                self._bus.get_object(BLUEZ_SERVICE_NAME, self._adapter_path),
                LE_ADVERTISING_MANAGER_IFACE
            )
            ad_manager.RegisterAdvertisement(
                self._advertisement.path,
                {},
                reply_handler=self._register_ad_callback,
                error_handler=self._register_ad_error
            )
        except Exception as e:
            print(f"[BLE Publisher] Error registering advertisement: {e}")
    
    def _register_ad_callback(self):
        print("[BLE Publisher] Advertisement registered successfully")
    
    def _register_ad_error(self, error):
        print(f"[BLE Publisher] Failed to register advertisement: {error}")
    
    def _cleanup(self):
        """Clean up D-Bus objects."""
        try:
            if self._advertisement and self._adapter_path:
                ad_manager = dbus.Interface(
                    self._bus.get_object(BLUEZ_SERVICE_NAME, self._adapter_path),
                    LE_ADVERTISING_MANAGER_IFACE
                )
                ad_manager.UnregisterAdvertisement(self._advertisement.path)
        except Exception:
            pass
        
        try:
            if self._application and self._adapter_path:
                gatt_manager = dbus.Interface(
                    self._bus.get_object(BLUEZ_SERVICE_NAME, self._adapter_path),
                    GATT_MANAGER_IFACE
                )
                gatt_manager.UnregisterApplication(self._application.get_path())
        except Exception:
            pass
    
    def _get_advertising_data(self) -> bytes:
        """Generate manufacturer data for advertising."""
        gps_fix = GPSFixStatus.NO_FIX
        try:
            import gps_client as gc
            status = gc.get_gps_status()
            if status and status.fix_ok:
                gps_fix = GPSFixStatus.FIX_3D if status.mode == 3 else GPSFixStatus.FIX_2D
        except Exception:
            pass
        
        bt_count, wifi_count = 0, 0
        if self._poller:
            bt_count, wifi_count = self._poller.get_counts()
        
        return encode_advertising_manufacturer_data(gps_fix, bt_count, wifi_count)
    
    def _poll_loop(self):
        """Background thread: poll database for new sightings."""
        last_notification = 0
        aggregation_interval = self.aggregation_ms / 1000.0
        
        while self._running:
            try:
                if not self._paused and self._subscribers > 0:
                    # Poll for new BT sightings
                    bt_sightings = self._poller.poll_bt_sightings(
                        min_rssi=self.min_rssi, limit=20
                    )
                    
                    # Poll for new WiFi sightings
                    wifi_sightings = self._poller.poll_wifi_sightings(
                        min_rssi=self.min_rssi, limit=20
                    )
                    
                    now = time.time()
                    
                    # Send notifications with rate limiting
                    for sighting in bt_sightings:
                        if now - last_notification >= aggregation_interval:
                            self._send_bt_notification(sighting)
                            last_notification = now
                            self._bt_sent += 1
                        else:
                            # Queue for later
                            self._queue.put(("bt", sighting))
                    
                    for sighting in wifi_sightings:
                        if now - last_notification >= aggregation_interval:
                            self._send_wifi_notification(sighting)
                            last_notification = now
                            self._wifi_sent += 1
                        else:
                            self._queue.put(("wifi", sighting))
                    
                    # Process queued items
                    while not self._queue.empty():
                        now = time.time()
                        if now - last_notification >= aggregation_interval:
                            try:
                                item_type, sighting = self._queue.get_nowait()
                                if item_type == "bt":
                                    self._send_bt_notification(sighting)
                                    self._bt_sent += 1
                                else:
                                    self._send_wifi_notification(sighting)
                                    self._wifi_sent += 1
                                last_notification = now
                            except Empty:
                                break
                        else:
                            break
                
                time.sleep(self.poll_interval)
                
            except Exception as e:
                print(f"[BLE Publisher] Poll error: {e}")
                time.sleep(1)
    
    def _send_bt_notification(self, sighting: BTSighting):
        """Send a BT sighting notification."""
        if not self._service:
            return
        
        self._seq_num = (self._seq_num + 1) % 65536
        data = encode_bt_sighting(sighting, self._seq_num)
        self._service.live_feed_char.send_notification(data)
    
    def _send_wifi_notification(self, sighting: WiFiSighting):
        """Send a WiFi sighting notification."""
        if not self._service:
            return
        
        self._seq_num = (self._seq_num + 1) % 65536
        data = encode_wifi_sighting(sighting, self._seq_num)
        self._service.live_feed_char.send_notification(data)
    
    # ========================================================================
    # GATT Characteristic Handlers
    # ========================================================================
    
    def on_live_feed_subscribe(self):
        """Called when a client subscribes to LiveFeed."""
        self._subscribers += 1
        print(f"[BLE Publisher] Subscriber connected (total: {self._subscribers})")
    
    def on_live_feed_unsubscribe(self):
        """Called when a client unsubscribes from LiveFeed."""
        self._subscribers = max(0, self._subscribers - 1)
        print(f"[BLE Publisher] Subscriber disconnected (total: {self._subscribers})")
    
    def on_control_write(self, data: bytes):
        """Handle control command from client."""
        try:
            cmd, payload = decode_control_command(data)
            print(f"[BLE Publisher] Control command: {cmd.name}")
            
            if cmd == ControlCommand.PAUSE_FEED:
                self._paused = True
                print("[BLE Publisher] Feed paused")
            
            elif cmd == ControlCommand.RESUME_FEED:
                self._paused = False
                print("[BLE Publisher] Feed resumed")
            
            elif cmd == ControlCommand.SET_RSSI_FILTER:
                if len(payload) >= 1:
                    self.min_rssi = struct.unpack("<b", payload[0:1])[0]
                    print(f"[BLE Publisher] RSSI filter set to {self.min_rssi} dBm")
            
            elif cmd == ControlCommand.SET_AGGREGATION_INTERVAL:
                if len(payload) >= 2:
                    self.aggregation_ms = struct.unpack("<H", payload[0:2])[0]
                    print(f"[BLE Publisher] Aggregation interval set to {self.aggregation_ms} ms")
            
            elif cmd == ControlCommand.PING:
                print("[BLE Publisher] Ping received")
                # Update status to send back via Status characteristic
                if self._service:
                    status_bytes = self.get_status_bytes()
                    self._service.status_char.send_notification(status_bytes)
            
            elif cmd == ControlCommand.GET_STATS:
                if self._service:
                    status_bytes = self.get_status_bytes()
                    self._service.status_char.send_notification(status_bytes)
            
        except Exception as e:
            print(f"[BLE Publisher] Control command error: {e}")
    
    def get_status_bytes(self) -> bytes:
        """Get current status as encoded bytes."""
        gps_fix = GPSFixStatus.NO_FIX
        gps_sats = None
        time_source = "system"
        
        try:
            import gps_client as gc
            status = gc.get_gps_status()
            if status:
                gps_fix = status.mode
                gps_sats = status.sats_used
                if status.fix_ok:
                    time_source = "gps"
        except Exception:
            pass
        
        bt_count, wifi_count = 0, 0
        if self._poller:
            bt_count, wifi_count = self._poller.get_counts()
        
        queue_depth = self._queue.qsize()
        
        status = ScannerStatus(
            gps_fix=gps_fix,
            gps_sats=gps_sats,
            time_source=time_source,
            timestamp=int(time.time()),
            queue_depth=queue_depth,
            scanner_id=SCANNER_ID,
            version=__version__,
            bt_sightings_total=bt_count,
            wifi_sightings_total=wifi_count,
            ble_publish_active=self._running,
            feed_paused=self._paused
        )
        
        return encode_status(status)
    
    def on_bulk_request(self, data: bytes, characteristic):
        """Handle bulk transfer request."""
        try:
            request = decode_bulk_request(data)
            print(f"[BLE Publisher] Bulk request: {request.ts_start} to {request.ts_end}, type={request.sighting_type}")
            
            # Get sightings from database
            packets = self._poller.get_bulk_sightings(
                request.ts_start, request.ts_end, request.sighting_type
            )
            
            if not packets:
                print("[BLE Publisher] No sightings in requested range")
                # Send empty response
                chunk = BulkChunk(chunk_id=0, total_chunks=0, data=b"")
                characteristic.send_notification(encode_bulk_chunk(chunk))
                return
            
            # Chunk and send (max ~500 bytes per chunk to fit MTU)
            CHUNK_SIZE = 480
            total_data = b"".join(packets)
            total_chunks = (len(total_data) + CHUNK_SIZE - 1) // CHUNK_SIZE
            
            print(f"[BLE Publisher] Sending {total_chunks} chunks ({len(total_data)} bytes)")
            
            for i in range(total_chunks):
                start = i * CHUNK_SIZE
                end = min(start + CHUNK_SIZE, len(total_data))
                chunk_data = total_data[start:end]
                
                chunk = BulkChunk(chunk_id=i, total_chunks=total_chunks, data=chunk_data)
                characteristic.send_notification(encode_bulk_chunk(chunk))
                
                # Small delay between chunks
                time.sleep(0.05)
            
            print(f"[BLE Publisher] Bulk transfer complete")
            
        except Exception as e:
            print(f"[BLE Publisher] Bulk request error: {e}")


# ============================================================================
# Standalone Execution
# ============================================================================

def main():
    """Main entry point for standalone execution."""
    import argparse
    
    parser = argparse.ArgumentParser(description="BLE GATT Publisher for SAR Scanner")
    parser.add_argument("--interface", "-i", default="hci0", 
                        help="Bluetooth interface (default: hci0)")
    parser.add_argument("--name", "-n", default="SAR-Scanner",
                        help="BLE device name (default: SAR-Scanner)")
    parser.add_argument("--db", "-d", default=None,
                        help="Path to SQLite database")
    parser.add_argument("--poll-interval", "-p", type=float, default=0.5,
                        help="Database poll interval in seconds (default: 0.5)")
    parser.add_argument("--min-rssi", "-r", type=int, default=-100,
                        help="Minimum RSSI filter in dBm (default: -100)")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("SAR Scanner BLE GATT Publisher")
    print("=" * 60)
    
    publisher = BLEGATTPublisher(
        db_path=args.db,
        interface=args.interface,
        device_name=args.name,
        poll_interval=args.poll_interval,
        min_rssi=args.min_rssi
    )
    
    # Handle Ctrl+C
    def signal_handler(sig, frame):
        print("\n[BLE Publisher] Shutting down...")
        publisher.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    publisher.run()


if __name__ == "__main__":
    main()
