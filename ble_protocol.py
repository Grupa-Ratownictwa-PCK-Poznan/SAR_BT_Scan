"""
BLE GATT Protocol definitions for SAR Scanner.

This module defines UUIDs, packet formats, and encoding/decoding functions
for the BLE GATT communication between the Raspberry Pi scanner and companion app.

Protocol Version: 1.0
"""

import struct
import json
from dataclasses import dataclass
from typing import Optional, List, Tuple
from enum import IntEnum

# ============================================================================
# Service and Characteristic UUIDs
# ============================================================================

# Custom Service UUID for SAR Scanner
SERVICE_UUID = "12345678-1234-5678-1234-56789abc0001"

# Characteristic UUIDs
CHAR_LIVE_FEED_UUID = "12345678-1234-5678-1234-56789abc0002"    # Notify
CHAR_CONTROL_UUID = "12345678-1234-5678-1234-56789abc0003"      # Write
CHAR_STATUS_UUID = "12345678-1234-5678-1234-56789abc0004"       # Read, Notify
CHAR_BULK_TRANSFER_UUID = "12345678-1234-5678-1234-56789abc0005"  # Notify, Write

# ============================================================================
# Protocol Constants
# ============================================================================

PROTOCOL_VERSION = 1
MAX_MTU = 512  # Negotiated MTU (default 23, can be up to 512)
DEFAULT_MTU = 20  # Safe default for notifications (23 - 3 overhead)

# ============================================================================
# Sighting Types
# ============================================================================

class SightingType(IntEnum):
    BLUETOOTH = 0x01
    WIFI = 0x02


# ============================================================================
# Control Commands
# ============================================================================

class ControlCommand(IntEnum):
    PAUSE_FEED = 0x01
    RESUME_FEED = 0x02
    SET_RSSI_FILTER = 0x10
    SET_AGGREGATION_INTERVAL = 0x20
    REQUEST_BULK_TRANSFER = 0x30
    PING = 0x40
    GET_STATS = 0x41


# ============================================================================
# GPS Fix Status
# ============================================================================

class GPSFixStatus(IntEnum):
    NO_FIX = 0
    FIX_2D = 2
    FIX_3D = 3


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class BTSighting:
    """Bluetooth sighting data structure."""
    addr: str
    ts_unix: int
    ts_gps: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    rssi: Optional[int]
    local_name: Optional[str]
    manufacturer: Optional[str]
    manufacturer_hex: Optional[str]
    tx_power: Optional[int] = None


@dataclass
class WiFiSighting:
    """WiFi association sighting data structure."""
    mac: str
    ts_unix: int
    ts_gps: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    ssid: str
    rssi: Optional[int]


@dataclass
class ScannerStatus:
    """Scanner status data structure."""
    gps_fix: int  # GPSFixStatus
    gps_sats: Optional[int]
    time_source: str  # "gps", "rtc", "system"
    timestamp: int
    queue_depth: int
    scanner_id: str
    version: str
    bt_sightings_total: int
    wifi_sightings_total: int
    ble_publish_active: bool
    feed_paused: bool


# ============================================================================
# Encoding Functions
# ============================================================================

def encode_mac(mac_str: str) -> bytes:
    """
    Encode MAC address string to 6 bytes.
    Accepts formats: "AA:BB:CC:DD:EE:FF" or "AA-BB-CC-DD-EE-FF"
    """
    mac_str = mac_str.replace(":", "").replace("-", "")
    return bytes.fromhex(mac_str)


def decode_mac(mac_bytes: bytes) -> str:
    """Decode 6 bytes to MAC address string."""
    return ":".join(f"{b:02X}" for b in mac_bytes)


def encode_lat_lon(lat: Optional[float], lon: Optional[float]) -> Tuple[bytes, bytes]:
    """
    Encode latitude and longitude as signed 32-bit integers (×10^7).
    Returns (lat_bytes, lon_bytes), each 4 bytes.
    """
    if lat is None:
        lat_int = 0x7FFFFFFF  # Sentinel for "no GPS"
    else:
        lat_int = int(lat * 1e7)
    
    if lon is None:
        lon_int = 0x7FFFFFFF
    else:
        lon_int = int(lon * 1e7)
    
    return struct.pack("<i", lat_int), struct.pack("<i", lon_int)


def decode_lat_lon(lat_bytes: bytes, lon_bytes: bytes) -> Tuple[Optional[float], Optional[float]]:
    """Decode latitude and longitude from bytes."""
    lat_int = struct.unpack("<i", lat_bytes)[0]
    lon_int = struct.unpack("<i", lon_bytes)[0]
    
    lat = None if lat_int == 0x7FFFFFFF else lat_int / 1e7
    lon = None if lon_int == 0x7FFFFFFF else lon_int / 1e7
    
    return lat, lon


def encode_bt_sighting(sighting: BTSighting, seq_num: int = 0) -> bytes:
    """
    Encode a Bluetooth sighting for BLE notification.
    
    Format (27 bytes base + variable name):
    - Type (1B): 0x01
    - Seq# (2B): Sequence number (little-endian)
    - MAC (6B): Device address
    - TS (4B): Unix timestamp (little-endian)
    - Lat (4B): Latitude × 10^7 (signed, little-endian)
    - Lon (4B): Longitude × 10^7 (signed, little-endian)
    - RSSI (1B): Signal strength (signed)
    - TX Power (1B): TX power or 0x7F if unknown
    - Flags (1B): bit0=has_name, bit1=has_manufacturer
    - Name length (1B): Length of name (0 if no name)
    - Mfr length (1B): Length of manufacturer (0 if no mfr)
    - Name (var): UTF-8 encoded name (truncated to fit MTU)
    - Manufacturer (var): UTF-8 manufacturer string
    """
    lat_bytes, lon_bytes = encode_lat_lon(sighting.lat, sighting.lon)
    
    rssi = sighting.rssi if sighting.rssi is not None else -128
    tx_power = sighting.tx_power if sighting.tx_power is not None else 127
    
    # Prepare optional strings
    name = (sighting.local_name or "")[:32].encode("utf-8")  # Truncate to 32 chars
    mfr = (sighting.manufacturer or "")[:20].encode("utf-8")  # Truncate to 20 chars
    
    flags = 0
    if name:
        flags |= 0x01
    if mfr:
        flags |= 0x02
    
    packet = bytearray()
    packet.append(SightingType.BLUETOOTH)  # Type
    packet.extend(struct.pack("<H", seq_num))  # Seq#
    packet.extend(encode_mac(sighting.addr))  # MAC
    packet.extend(struct.pack("<I", int(sighting.ts_unix)))  # Timestamp
    packet.extend(lat_bytes)  # Lat
    packet.extend(lon_bytes)  # Lon
    packet.extend(struct.pack("<b", rssi))  # RSSI (signed)
    packet.extend(struct.pack("<b", tx_power))  # TX Power (signed)
    packet.append(flags)  # Flags
    packet.append(len(name))  # Name length
    packet.append(len(mfr))  # Manufacturer length
    packet.extend(name)  # Name data
    packet.extend(mfr)  # Manufacturer data
    
    return bytes(packet)


def decode_bt_sighting(data: bytes) -> Tuple[BTSighting, int]:
    """
    Decode a Bluetooth sighting from BLE notification bytes.
    Returns (BTSighting, seq_num).
    """
    if len(data) < 27:
        raise ValueError(f"Packet too short: {len(data)} bytes")
    
    sighting_type = data[0]
    if sighting_type != SightingType.BLUETOOTH:
        raise ValueError(f"Invalid sighting type: {sighting_type}")
    
    seq_num = struct.unpack("<H", data[1:3])[0]
    mac = decode_mac(data[3:9])
    ts_unix = struct.unpack("<I", data[9:13])[0]
    lat, lon = decode_lat_lon(data[13:17], data[17:21])
    rssi = struct.unpack("<b", data[21:22])[0]
    tx_power = struct.unpack("<b", data[22:23])[0]
    flags = data[23]
    name_len = data[24]
    mfr_len = data[25]
    
    offset = 26
    name = data[offset:offset + name_len].decode("utf-8") if name_len > 0 else None
    offset += name_len
    mfr = data[offset:offset + mfr_len].decode("utf-8") if mfr_len > 0 else None
    
    if rssi == -128:
        rssi = None
    if tx_power == 127:
        tx_power = None
    
    sighting = BTSighting(
        addr=mac,
        ts_unix=ts_unix,
        ts_gps=None,
        lat=lat,
        lon=lon,
        rssi=rssi,
        local_name=name,
        manufacturer=mfr,
        manufacturer_hex=None,
        tx_power=tx_power
    )
    
    return sighting, seq_num


def encode_wifi_sighting(sighting: WiFiSighting, seq_num: int = 0) -> bytes:
    """
    Encode a WiFi sighting for BLE notification.
    
    Format (24 bytes base + variable SSID):
    - Type (1B): 0x02
    - Seq# (2B): Sequence number
    - MAC (6B): Device address
    - TS (4B): Unix timestamp
    - Lat (4B): Latitude × 10^7
    - Lon (4B): Longitude × 10^7
    - RSSI (1B): Signal strength
    - SSID length (1B)
    - SSID (var): UTF-8 encoded SSID (truncated to 32 chars)
    """
    lat_bytes, lon_bytes = encode_lat_lon(sighting.lat, sighting.lon)
    rssi = sighting.rssi if sighting.rssi is not None else -128
    ssid = (sighting.ssid or "")[:32].encode("utf-8")
    
    packet = bytearray()
    packet.append(SightingType.WIFI)  # Type
    packet.extend(struct.pack("<H", seq_num))  # Seq#
    packet.extend(encode_mac(sighting.mac))  # MAC
    packet.extend(struct.pack("<I", int(sighting.ts_unix)))  # Timestamp
    packet.extend(lat_bytes)  # Lat
    packet.extend(lon_bytes)  # Lon
    packet.extend(struct.pack("<b", rssi))  # RSSI
    packet.append(len(ssid))  # SSID length
    packet.extend(ssid)  # SSID data
    
    return bytes(packet)


def decode_wifi_sighting(data: bytes) -> Tuple[WiFiSighting, int]:
    """
    Decode a WiFi sighting from BLE notification bytes.
    Returns (WiFiSighting, seq_num).
    """
    if len(data) < 24:
        raise ValueError(f"Packet too short: {len(data)} bytes")
    
    sighting_type = data[0]
    if sighting_type != SightingType.WIFI:
        raise ValueError(f"Invalid sighting type: {sighting_type}")
    
    seq_num = struct.unpack("<H", data[1:3])[0]
    mac = decode_mac(data[3:9])
    ts_unix = struct.unpack("<I", data[9:13])[0]
    lat, lon = decode_lat_lon(data[13:17], data[17:21])
    rssi = struct.unpack("<b", data[21:22])[0]
    ssid_len = data[22]
    ssid = data[23:23 + ssid_len].decode("utf-8") if ssid_len > 0 else ""
    
    if rssi == -128:
        rssi = None
    
    sighting = WiFiSighting(
        mac=mac,
        ts_unix=ts_unix,
        ts_gps=None,
        lat=lat,
        lon=lon,
        ssid=ssid,
        rssi=rssi
    )
    
    return sighting, seq_num


def encode_status(status: ScannerStatus) -> bytes:
    """
    Encode scanner status as JSON bytes.
    Used for Status characteristic (Read/Notify).
    """
    data = {
        "v": PROTOCOL_VERSION,
        "gps_fix": status.gps_fix,
        "gps_sats": status.gps_sats,
        "time_src": status.time_source,
        "ts": status.timestamp,
        "queue": status.queue_depth,
        "id": status.scanner_id,
        "ver": status.version,
        "bt_cnt": status.bt_sightings_total,
        "wifi_cnt": status.wifi_sightings_total,
        "active": status.ble_publish_active,
        "paused": status.feed_paused
    }
    return json.dumps(data, separators=(",", ":")).encode("utf-8")


def decode_status(data: bytes) -> ScannerStatus:
    """Decode scanner status from JSON bytes."""
    d = json.loads(data.decode("utf-8"))
    return ScannerStatus(
        gps_fix=d.get("gps_fix", 0),
        gps_sats=d.get("gps_sats"),
        time_source=d.get("time_src", "system"),
        timestamp=d.get("ts", 0),
        queue_depth=d.get("queue", 0),
        scanner_id=d.get("id", ""),
        version=d.get("ver", ""),
        bt_sightings_total=d.get("bt_cnt", 0),
        wifi_sightings_total=d.get("wifi_cnt", 0),
        ble_publish_active=d.get("active", False),
        feed_paused=d.get("paused", False)
    )


def encode_control_command(cmd: ControlCommand, payload: bytes = b"") -> bytes:
    """Encode a control command for writing to Control characteristic."""
    return bytes([cmd]) + payload


def decode_control_command(data: bytes) -> Tuple[ControlCommand, bytes]:
    """Decode a control command from bytes."""
    if len(data) < 1:
        raise ValueError("Empty command")
    cmd = ControlCommand(data[0])
    payload = data[1:] if len(data) > 1 else b""
    return cmd, payload


# ============================================================================
# Bulk Transfer Protocol
# ============================================================================

@dataclass
class BulkRequest:
    """Request for bulk data transfer."""
    ts_start: int  # Unix timestamp start
    ts_end: int    # Unix timestamp end
    sighting_type: int  # 0=both, 1=BT only, 2=WiFi only


@dataclass
class BulkChunk:
    """A chunk of bulk transfer data."""
    chunk_id: int
    total_chunks: int
    data: bytes


def encode_bulk_request(request: BulkRequest) -> bytes:
    """Encode a bulk transfer request."""
    return struct.pack("<IIB", request.ts_start, request.ts_end, request.sighting_type)


def decode_bulk_request(data: bytes) -> BulkRequest:
    """Decode a bulk transfer request."""
    if len(data) < 9:
        raise ValueError(f"Bulk request too short: {len(data)} bytes")
    ts_start, ts_end, sighting_type = struct.unpack("<IIB", data[:9])
    return BulkRequest(ts_start=ts_start, ts_end=ts_end, sighting_type=sighting_type)


def encode_bulk_chunk(chunk: BulkChunk) -> bytes:
    """Encode a bulk transfer chunk."""
    header = struct.pack("<HH", chunk.chunk_id, chunk.total_chunks)
    return header + chunk.data


def decode_bulk_chunk(data: bytes) -> BulkChunk:
    """Decode a bulk transfer chunk."""
    if len(data) < 4:
        raise ValueError(f"Bulk chunk too short: {len(data)} bytes")
    chunk_id, total_chunks = struct.unpack("<HH", data[:4])
    return BulkChunk(chunk_id=chunk_id, total_chunks=total_chunks, data=data[4:])


# ============================================================================
# Advertising Data
# ============================================================================

def encode_advertising_manufacturer_data(
    gps_fix: int,
    bt_count: int,
    wifi_count: int
) -> bytes:
    """
    Encode manufacturer data for BLE advertisement.
    
    Format (8 bytes):
    - Protocol version (1B)
    - GPS fix status (1B)
    - BT sighting count (3B, little-endian, max ~16M)
    - WiFi sighting count (3B, little-endian)
    """
    # Clamp counts to 3 bytes max (16,777,215)
    bt_count = min(bt_count, 0xFFFFFF)
    wifi_count = min(wifi_count, 0xFFFFFF)
    
    packet = bytearray()
    packet.append(PROTOCOL_VERSION)
    packet.append(gps_fix)
    # Pack 3-byte integers (little-endian)
    packet.extend(struct.pack("<I", bt_count)[:3])
    packet.extend(struct.pack("<I", wifi_count)[:3])
    
    return bytes(packet)


def decode_advertising_manufacturer_data(data: bytes) -> dict:
    """Decode manufacturer data from BLE advertisement."""
    if len(data) < 8:
        raise ValueError(f"Manufacturer data too short: {len(data)} bytes")
    
    version = data[0]
    gps_fix = data[1]
    bt_count = struct.unpack("<I", data[2:5] + b"\x00")[0]
    wifi_count = struct.unpack("<I", data[5:8] + b"\x00")[0]
    
    return {
        "version": version,
        "gps_fix": gps_fix,
        "bt_count": bt_count,
        "wifi_count": wifi_count
    }
