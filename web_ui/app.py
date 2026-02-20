"""
Web UI Server for SAR BT+WiFi Scanner

A FastAPI-based web application that provides:
- Live data preview with WebSocket updates
- GPS fix and scanner mode indicators
- Filtered data tables for BT, WiFi, and association requests
- Interactive map with heatmap overlay

The server connects to the scanner's database for data retrieval
and status information from main.py.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import time
import threading
import shutil
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import sys
import os
import psutil
import subprocess

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from settings import WEB_UI_HOST, WEB_UI_PORT, WEB_UI_REFRESH_INTERVAL, DB_FILE, SD_STORAGE, USB_STORAGE
from storage import db
from .mac_utils import lookup_randomized_mac_vendor, is_locally_administered_mac
import gps_client as gc

app = FastAPI(title="SAR Scanner UI", description="Live web interface for SAR BT+WiFi Scanner")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = SD_STORAGE + DB_FILE

# Check if the configured database exists; if not, try fallback paths for testing
if not os.path.exists(DB_PATH):
    if os.path.exists('/tmp/test_results.db'):
        DB_PATH = '/tmp/test_results.db'
    elif os.path.exists('./test_results.db'):
        DB_PATH = './test_results.db'

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()


# Global state tracking
class ScannerState:
    def __init__(self):
        self.scanner_mode = None
        self.wifi_monitor_mode = False
        self.last_update = time.time()

state = ScannerState()


def get_db_path():
    """Get database path."""
    return DB_PATH


def query_devices(device_type: str, limit: int = 1000, offset: int = 0, 
                  filters: Optional[Dict] = None) -> List[Dict]:
    """Query devices from database with optional filters.
    
    Args:
        device_type: "bt" or "wifi"
        limit: Maximum number of results
        offset: Pagination offset
        filters: Optional dict with filter keys:
                - mac_filter: MAC address substring
                - confidence_min: Minimum confidence (0-100)
                - confidence_max: Maximum confidence (0-100)
                - rssi_min: Minimum RSSI
                - rssi_max: Maximum RSSI
                - time_start: Unix timestamp
                - time_end: Unix timestamp
    """
    filters = filters or {}
    results = []
    
    try:
        with db() as con:
            if device_type == "bt":
                query = "SELECT addr, first_seen, last_seen, name, manufacturer_hex, manufacturer, confidence, notes FROM devices ORDER BY last_seen DESC"
                cursor = con.execute(query)
                
                for row in cursor.fetchall():
                    addr, first_seen, last_seen, name, manufacturer_hex, manufacturer, confidence, notes = row
                    
                    # Filter by MAC if specified
                    if "mac_filter" in filters and filters["mac_filter"].lower() not in addr.lower():
                        continue
                    
                    # Filter by confidence if specified
                    if "confidence_min" in filters and confidence < filters["confidence_min"]:
                        continue
                    if "confidence_max" in filters and confidence > filters["confidence_max"]:
                        continue
                    
                    results.append({
                        "type": "device",
                        "mac": addr,
                        "name": name,
                        "manufacturer": manufacturer,
                        "manufacturer_hex": manufacturer_hex,
                        "first_seen": first_seen,
                        "last_seen": last_seen,
                        "last_seen_str": datetime.fromtimestamp(last_seen).isoformat(),
                        "confidence": confidence,
                        "notes": notes or ""
                    })
            
            elif device_type == "wifi":
                query = "SELECT mac, first_seen, last_seen, vendor, device_type, confidence, notes FROM wifi_devices ORDER BY last_seen DESC"
                cursor = con.execute(query)
                
                for row in cursor.fetchall():
                    mac, first_seen, last_seen, vendor, device_type_val, confidence, notes = row
                    
                    # Filter by MAC if specified
                    if "mac_filter" in filters and filters["mac_filter"].lower() not in mac.lower():
                        continue
                    
                    # Filter by confidence if specified
                    if "confidence_min" in filters and confidence < filters["confidence_min"]:
                        continue
                    if "confidence_max" in filters and confidence > filters["confidence_max"]:
                        continue
                    
                    # Try to recover vendor for randomized MACs
                    display_vendor = vendor or ""
                    if not display_vendor and is_locally_administered_mac(mac):
                        recovered_vendor, was_randomized = lookup_randomized_mac_vendor(mac)
                        if recovered_vendor:
                            display_vendor = recovered_vendor
                    
                    results.append({
                        "type": "device",
                        "mac": mac,
                        "vendor": display_vendor,
                        "device_type": device_type_val or "",
                        "first_seen": first_seen,
                        "last_seen": last_seen,
                        "last_seen_str": datetime.fromtimestamp(last_seen).isoformat(),
                        "confidence": confidence,
                        "notes": notes or ""
                    })
    
    except Exception as e:
        print(f"Error querying {device_type} devices: {e}")
    
    return results[offset:offset + limit]


def query_sightings(mac_filter: Optional[str] = None, 
                   rssi_min: Optional[int] = None,
                   rssi_max: Optional[int] = None,
                   time_start: Optional[float] = None,
                   time_end: Optional[float] = None,
                   limit: int = 500) -> List[Dict]:
    """Query BT sightings with filters."""
    results = []
    
    try:
        with db() as con:
            query = "SELECT * FROM sightings WHERE 1=1"
            params = []
            
            if mac_filter:
                query += " AND addr LIKE ?"
                params.append(f"%{mac_filter}%")
            
            if rssi_min is not None:
                query += " AND rssi >= ?"
                params.append(rssi_min)
            
            if rssi_max is not None:
                query += " AND rssi <= ?"
                params.append(rssi_max)
            
            if time_start is not None:
                query += " AND ts_unix >= ?"
                params.append(time_start)
            
            if time_end is not None:
                query += " AND ts_unix <= ?"
                params.append(time_end)
            
            query += " ORDER BY ts_unix DESC LIMIT ?"
            params.append(limit)
            
            cursor = con.execute(query, params)
            
            for row in cursor.fetchall():
                (id_, addr, ts_unix, ts_gps, lat, lon, alt, gps_hdop, rssi, tx_power, 
                 local_name, manufacturer, manufacturer_hex, service_uuid, scanner_name, adv_raw) = row
                
                results.append({
                    "id": id_,
                    "mac": addr,
                    "timestamp": ts_unix,
                    "timestamp_str": datetime.fromtimestamp(ts_unix).isoformat(),
                    "gps_timestamp": ts_gps,
                    "lat": lat,
                    "lon": lon,
                    "alt": alt,
                    "gps_hdop": gps_hdop,
                    "rssi": rssi,
                    "tx_power": tx_power,
                    "name": local_name,
                    "manufacturer": manufacturer,
                    "manufacturer_hex": manufacturer_hex,
                    "service_uuid": service_uuid,
                    "scanner": scanner_name
                })
    
    except Exception as e:
        print(f"Error querying sightings: {e}")
    
    return results


def query_wifi_associations(mac_filter: Optional[str] = None,
                           ssid_filter: Optional[str] = None,
                           rssi_min: Optional[int] = None,
                           rssi_max: Optional[int] = None,
                           time_start: Optional[float] = None,
                           time_end: Optional[float] = None,
                           limit: int = 500) -> List[Dict]:
    """Query WiFi association requests with filters."""
    results = []
    
    try:
        with db() as con:
            query = "SELECT * FROM wifi_associations WHERE 1=1"
            params = []
            
            if mac_filter:
                query += " AND mac LIKE ?"
                params.append(f"%{mac_filter}%")
            
            if ssid_filter:
                query += " AND ssid LIKE ?"
                params.append(f"%{ssid_filter}%")
            
            if rssi_min is not None:
                query += " AND rssi >= ?"
                params.append(rssi_min)
            
            if rssi_max is not None:
                query += " AND rssi <= ?"
                params.append(rssi_max)
            
            if time_start is not None:
                query += " AND ts_unix >= ?"
                params.append(time_start)
            
            if time_end is not None:
                query += " AND ts_unix <= ?"
                params.append(time_end)
            
            query += " ORDER BY ts_unix DESC LIMIT ?"
            params.append(limit)
            
            cursor = con.execute(query, params)
            
            for row in cursor.fetchall():
                (id_, mac, ts_unix, ts_gps, lat, lon, alt, ssid, packet_type, rssi, scanner_name) = row
                
                results.append({
                    "id": id_,
                    "mac": mac,
                    "timestamp": ts_unix,
                    "timestamp_str": datetime.fromtimestamp(ts_unix).isoformat(),
                    "gps_timestamp": ts_gps,
                    "lat": lat,
                    "lon": lon,
                    "alt": alt,
                    "ssid": ssid,
                    "packet_type": packet_type,
                    "rssi": rssi,
                    "scanner": scanner_name
                })
    
    except Exception as e:
        print(f"Error querying WiFi associations: {e}")
    
    return results


def get_wifi_adapter_bands(interface: str) -> str:
    """Detect WiFi adapter band support (2.4 GHz, 5 GHz, or both).
    
    Uses 'iw list' to query adapter capabilities.
    Returns string like '2.4 GHz', '5 GHz', or '2.4 & 5 GHz'.
    """
    try:
        result = subprocess.run(
            ["iw", "list"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        output = result.stdout
        has_2ghz = "2400-2500 MHz" in output or "Band 1:" in output or "Channel 1" in output
        has_5ghz = "5000-6000 MHz" in output or "Band 2:" in output or "Channel 36" in output or "5180 MHz" in output
        
        if has_2ghz and has_5ghz:
            return "2.4 & 5 GHz"
        elif has_5ghz:
            return "5 GHz"
        elif has_2ghz:
            return "2.4 GHz"
        else:
            return "unknown"
    except Exception as e:
        return f"error: {str(e)[:20]}"


# ============= API Endpoints =============

@app.get("/api/status")
async def get_status():
    """Get current scanner status: GPS fix, mode, uptime."""
    from settings import WIFI_INTERFACE
    
    gps_status = gc.get_gps_status()
    gps_loc = gc.get_location()
    
    # Detect WiFi adapter bands
    wifi_bands = get_wifi_adapter_bands(WIFI_INTERFACE)
    
    return {
        "timestamp": time.time(),
        "timestamp_str": datetime.now(timezone.utc).isoformat(),
        "gps": {
            "fix_ok": gps_status.fix_ok if gps_status else False,
            "mode": gps_status.mode if gps_status else 0,
            "sats_used": gps_status.sats_used if gps_status else None,
            "hdop": gps_status.hdop if gps_status else None,
            "vdop": gps_status.vdop if gps_status else None,
            "pdop": gps_status.pdop if gps_status else None,
            "epx": gps_status.epx if gps_status else None,
            "epy": gps_status.epy if gps_status else None,
            "epv": gps_status.epv if gps_status else None,
            "location": {
                "lat": gps_loc.lat if gps_loc else None,
                "lon": gps_loc.lon if gps_loc else None,
                "alt": gps_loc.alt if gps_loc else None,
            } if gps_loc else None
        },
        "scanner": {
            "mode": state.scanner_mode,
            "wifi_monitor_mode": state.wifi_monitor_mode,
            "wifi_bands": wifi_bands
        }
    }


@app.get("/api/bt/devices")
async def get_bt_devices(limit: int = Query(100, ge=1, le=1000),
                        offset: int = Query(0, ge=0),
                        mac_filter: Optional[str] = None,
                        confidence_min: Optional[int] = Query(None, ge=0, le=100),
                        confidence_max: Optional[int] = Query(None, ge=0, le=100)):
    """Get BT devices list with optional filters."""
    filters = {}
    if mac_filter:
        filters["mac_filter"] = mac_filter
    if confidence_min is not None:
        filters["confidence_min"] = confidence_min
    if confidence_max is not None:
        filters["confidence_max"] = confidence_max
    
    devices = query_devices("bt", limit=limit, offset=offset, filters=filters)
    return {"devices": devices, "count": len(devices)}


@app.get("/api/bt/sightings")
async def get_bt_sightings(
    limit: int = Query(500, ge=1, le=2000),
    mac_filter: Optional[str] = None,
    rssi_min: Optional[int] = Query(None, ge=-100, le=0),
    rssi_max: Optional[int] = Query(None, ge=-100, le=0),
    hours_back: Optional[int] = Query(None, ge=0),
    time_start: Optional[float] = None,
    time_end: Optional[float] = None
):
    """Get BT sightings with filters.
    
    Can use either hours_back (quick select) or time_start/time_end (custom range).
    time_start and time_end take precedence if provided.
    """
    time_start_unix = None
    if time_start is not None:
        time_start_unix = time_start
    elif hours_back:
        time_start_unix = time.time() - (hours_back * 3600)
    
    sightings = query_sightings(
        mac_filter=mac_filter,
        rssi_min=rssi_min,
        rssi_max=rssi_max,
        time_start=time_start_unix,
        time_end=time_end,
        limit=limit
    )
    return {"sightings": sightings, "count": len(sightings)}


@app.get("/api/wifi/devices")
async def get_wifi_devices(limit: int = Query(100, ge=1, le=1000),
                          offset: int = Query(0, ge=0),
                          mac_filter: Optional[str] = None,
                          confidence_min: Optional[int] = Query(None, ge=0, le=100),
                          confidence_max: Optional[int] = Query(None, ge=0, le=100)):
    """Get WiFi devices list with optional filters."""
    filters = {}
    if mac_filter:
        filters["mac_filter"] = mac_filter
    if confidence_min is not None:
        filters["confidence_min"] = confidence_min
    if confidence_max is not None:
        filters["confidence_max"] = confidence_max
    
    devices = query_devices("wifi", limit=limit, offset=offset, filters=filters)
    return {"devices": devices, "count": len(devices)}


@app.get("/api/wifi/associations")
async def get_wifi_associations(
    limit: int = Query(500, ge=1, le=2000),
    mac_filter: Optional[str] = None,
    ssid_filter: Optional[str] = None,
    rssi_min: Optional[int] = Query(None, ge=-100, le=0),
    rssi_max: Optional[int] = Query(None, ge=-100, le=0),
    hours_back: Optional[int] = Query(None, ge=0),
    time_start: Optional[float] = None,
    time_end: Optional[float] = None
):
    """Get WiFi association requests with filters.
    
    Can use either hours_back (quick select) or time_start/time_end (custom range).
    time_start and time_end take precedence if provided.
    """
    time_start_unix = None
    if time_start is not None:
        time_start_unix = time_start
    elif hours_back:
        time_start_unix = time.time() - (hours_back * 3600)
    
    associations = query_wifi_associations(
        mac_filter=mac_filter,
        ssid_filter=ssid_filter,
        rssi_min=rssi_min,
        rssi_max=rssi_max,
        time_start=time_start_unix,
        time_end=time_end,
        limit=limit
    )
    return {"associations": associations, "count": len(associations)}


@app.get("/api/wifi/device/{mac}/ssids")
async def get_wifi_device_ssids(mac: str):
    """Get SSIDs associated with a specific WiFi device MAC address with packet type information.
    
    Returns detailed SSID information including whether the device is probing for them
    (ProbeRequest) or advertising them (Beacon). Also includes device-level metadata.
    """
    ssids_data = []
    device_info = {}
    
    try:
        with db() as con:
            # Get device information
            device_query = "SELECT vendor, device_type, confidence, notes, first_seen, last_seen FROM wifi_devices WHERE mac = ?"
            device_cursor = con.execute(device_query, (mac,))
            device_row = device_cursor.fetchone()
            
            if device_row:
                vendor, device_type, confidence, notes, first_seen, last_seen = device_row
                device_info = {
                    "vendor": vendor or "Unknown",
                    "device_type": device_type or "Unknown",
                    "confidence": confidence or 0,
                    "notes": notes or "",
                    "first_seen": first_seen,
                    "last_seen": last_seen,
                    "first_seen_str": datetime.fromtimestamp(first_seen).isoformat(),
                    "last_seen_str": datetime.fromtimestamp(last_seen).isoformat()
                }
            
            # Get SSID details with packet type information
            query = """
                SELECT DISTINCT ssid, packet_type, COUNT(*) as count,
                       MAX(ts_unix) as last_seen_ts, AVG(rssi) as avg_rssi
                FROM wifi_associations 
                WHERE mac = ?
                GROUP BY ssid, packet_type
                ORDER BY ssid, packet_type DESC
            """
            cursor = con.execute(query, (mac,))
            
            ssid_dict = {}  # Group by SSID to combine packet types
            for row in cursor.fetchall():
                ssid, packet_type, count, last_seen_ts, avg_rssi = row
                if ssid:  # Skip null/empty SSIDs
                    if ssid not in ssid_dict:
                        ssid_dict[ssid] = {
                            "ssid": ssid,
                            "types": [],
                            "count": 0,
                            "last_seen": 0,
                            "avg_rssi": 0
                        }
                    
                    ssid_dict[ssid]["types"].append({
                        "type": packet_type or "ProbeRequest",
                        "count": count,
                        "last_seen": last_seen_ts,
                        "avg_rssi": round(avg_rssi, 1) if avg_rssi else 0
                    })
                    ssid_dict[ssid]["count"] += count
                    ssid_dict[ssid]["last_seen"] = max(ssid_dict[ssid]["last_seen"], last_seen_ts or 0)
            
            ssids_data = sorted(ssid_dict.values(), key=lambda x: x["last_seen"], reverse=True)
    
    except Exception as e:
        print(f"Error querying SSIDs for device {mac}: {e}")
    
    return {
        "mac": mac,
        "device_info": device_info,
        "ssids": ssids_data,
        "count": len(ssids_data)
    }


@app.get("/api/map/heatmap")
async def get_heatmap_data(
    data_type: str = Query("all", regex="^(bt|wifi|assoc|all)$"),
    hours_back: Optional[int] = Query(None, ge=0),
    mac_filter: Optional[str] = None,
    ssid_filter: Optional[str] = None,
    rssi_min: Optional[int] = Query(None, ge=-100, le=0),
    rssi_max: Optional[int] = Query(None, ge=-100, le=0),
    time_start: Optional[float] = None,
    time_end: Optional[float] = None
):
    """Get heatmap data (GPS coordinates with RSSI) for map visualization with optional filters.
    
    Can use either hours_back (quick select) or time_start/time_end (custom range).
    time_start and time_end take precedence if provided.
    """
    time_start_unix = None
    if time_start is not None:
        time_start_unix = time_start
    elif hours_back:
        time_start_unix = time.time() - (hours_back * 3600)
    
    heatmap_points = []
    
    try:
        with db() as con:
            # BT sightings
            if data_type in ("bt", "all"):
                query = "SELECT lat, lon, rssi, addr, ts_unix FROM sightings WHERE lat IS NOT NULL AND lon IS NOT NULL"
                params = []
                
                if mac_filter:
                    query += " AND addr LIKE ?"
                    params.append(f"%{mac_filter}%")
                
                if rssi_min is not None:
                    query += " AND rssi >= ?"
                    params.append(rssi_min)
                
                if rssi_max is not None:
                    query += " AND rssi <= ?"
                    params.append(rssi_max)
                
                if time_start_unix:
                    query += " AND ts_unix >= ?"
                    params.append(time_start_unix)
                
                if time_end is not None:
                    query += " AND ts_unix <= ?"
                    params.append(time_end)
                
                cursor = con.execute(query, params)
                for lat, lon, rssi, mac, ts_unix in cursor.fetchall():
                    if lat and lon:
                        heatmap_points.append({
                            "lat": lat,
                            "lon": lon,
                            "rssi": rssi,
                            "type": "bt",
                            "mac": mac,
                            "timestamp": ts_unix,
                            "intensity": max(0, min(1, (rssi + 100) / 100))  # Normalize RSSI to 0-1
                        })
            
            # WiFi associations
            if data_type in ("wifi", "assoc", "all"):
                query = "SELECT lat, lon, rssi, mac, ssid, packet_type, ts_unix FROM wifi_associations WHERE lat IS NOT NULL AND lon IS NOT NULL"
                params = []
                
                if mac_filter:
                    query += " AND mac LIKE ?"
                    params.append(f"%{mac_filter}%")
                
                if ssid_filter:
                    query += " AND ssid LIKE ?"
                    params.append(f"%{ssid_filter}%")
                
                if rssi_min is not None:
                    query += " AND rssi >= ?"
                    params.append(rssi_min)
                
                if rssi_max is not None:
                    query += " AND rssi <= ?"
                    params.append(rssi_max)
                
                if time_start_unix:
                    query += " AND ts_unix >= ?"
                    params.append(time_start_unix)
                
                if time_end is not None:
                    query += " AND ts_unix <= ?"
                    params.append(time_end)
                
                cursor = con.execute(query, params)
                for lat, lon, rssi, mac, ssid, packet_type, ts_unix in cursor.fetchall():
                    if lat and lon:
                        heatmap_points.append({
                            "lat": lat,
                            "lon": lon,
                            "rssi": rssi,
                            "type": "assoc",
                            "mac": mac,
                            "ssid": ssid,
                            "packet_type": packet_type,
                            "timestamp": ts_unix,
                            "intensity": max(0, min(1, (rssi + 100) / 100))
                        })
    
    except Exception as e:
        print(f"Error querying heatmap data: {e}")
    
    return {"points": heatmap_points}


@app.websocket("/ws/live")
async def websocket_live_updates(websocket: WebSocket):
    """WebSocket endpoint for live data updates."""
    await manager.connect(websocket)
    try:
        while True:
            # Send live updates periodically
            await asyncio.sleep(WEB_UI_REFRESH_INTERVAL)
            
            try:
                # Get latest data
                gps_status = gc.get_gps_status()
                gps_loc = gc.get_location()
                
                # Get recent sightings and associations
                recent_sightings = query_sightings(limit=20)
                recent_assocs = query_wifi_associations(limit=20)
                
                # Count devices
                with db() as con:
                    bt_count = con.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
                    wifi_count = con.execute("SELECT COUNT(*) FROM wifi_devices").fetchone()[0]
                    sighting_count = con.execute("SELECT COUNT(*) FROM sightings").fetchone()[0]
                    assoc_count = con.execute("SELECT COUNT(*) FROM wifi_associations").fetchone()[0]
                
                update = {
                    "type": "live_update",
                    "timestamp": time.time(),
                    "gps": {
                        "fix_ok": gps_status.fix_ok if gps_status else False,
                        "sats_used": gps_status.sats_used if gps_status else None,
                        "hdop": gps_status.hdop if gps_status else None,
                        "location": {
                            "lat": gps_loc.lat if gps_loc else None,
                            "lon": gps_loc.lon if gps_loc else None,
                        } if gps_loc else None
                    },
                    "stats": {
                        "bt_devices": bt_count,
                        "wifi_devices": wifi_count,
                        "bt_sightings": sighting_count,
                        "wifi_associations": assoc_count,
                    },
                    "recent_sightings": recent_sightings[:5],
                    "recent_associations": recent_assocs[:5]
                }
                
                await websocket.send_json(update)
            except Exception as send_error:
                # Connection closed or send failed - break the loop
                if "CLOSED" in str(send_error) or "closed" in str(send_error):
                    break
                # Log other errors but continue
                print(f"Error sending WebSocket update: {send_error}")
    
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# ============= Static Files =============

@app.get("/")
async def get_index():
    """Serve the main UI HTML."""
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return HTMLResponse("<h1>SAR Scanner UI</h1><p>Starting up...</p>")


@app.get("/assets/{file_path:path}")
async def get_asset(file_path: str):
    """Serve static assets."""
    asset_path = os.path.join(os.path.dirname(__file__), "assets", file_path)
    if os.path.exists(asset_path):
        return FileResponse(asset_path)
    return JSONResponse({"error": "Not found"}, status_code=404)


@app.get("/static/{file_path:path}")
async def get_static(file_path: str):
    """Serve bundled static files (CSS, JS, webfonts) for offline operation."""
    static_path = os.path.join(os.path.dirname(__file__), "static", file_path)
    if os.path.exists(static_path):
        # Set appropriate content types
        if file_path.endswith('.css'):
            return FileResponse(static_path, media_type='text/css')
        elif file_path.endswith('.js'):
            return FileResponse(static_path, media_type='application/javascript')
        elif file_path.endswith('.woff2'):
            return FileResponse(static_path, media_type='font/woff2')
        elif file_path.endswith('.woff'):
            return FileResponse(static_path, media_type='font/woff')
        elif file_path.endswith('.ttf'):
            return FileResponse(static_path, media_type='font/ttf')
        return FileResponse(static_path)
    return JSONResponse({"error": "Not found"}, status_code=404)


@app.get("/api/download-db")
async def download_db():
    """Download the complete results.db database file."""
    db_path = get_db_path()
    if not os.path.exists(db_path):
        return JSONResponse({"error": "Database not found"}, status_code=404)
    
    return FileResponse(db_path, filename="results.db", media_type="application/octet-stream")


# ============= Triangulation Analysis =============

@app.get("/triangulate")
async def get_triangulation_page():
    """Serve the triangulation analysis page."""
    html_path = os.path.join(os.path.dirname(__file__), "triangulation.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return HTMLResponse("<h1>Triangulation Page Not Found</h1>")


@app.get("/api/triangulate/{mac}")
async def triangulate_device(mac: str):
    """Run triangulation and movement analysis for a specific device.
    
    Analyzes all sightings (BT and WiFi) for the device and determines:
    - Likely location(s)
    - Whether the device is stationary or moving
    - Movement path and speed statistics
    
    Args:
        mac: MAC address of the device to analyze
        
    Returns:
        TriangulationResult as JSON
    """
    try:
        # Import triangulation module
        from triangulation import DeviceTriangulator
        
        triangulator = DeviceTriangulator(mac)
        result = triangulator.analyze()
        
        if result is None:
            return JSONResponse(
                {"error": f"Device not found: {mac}"},
                status_code=404
            )
        
        return result.to_dict()
    
    except Exception as e:
        print(f"Error in triangulation analysis for {mac}: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            {"error": f"Triangulation failed: {str(e)}"},
            status_code=500
        )


@app.post("/api/purge-db")
async def purge_db():
    """Purge all tables in the database and create a backup."""
    db_path = get_db_path()
    
    if not os.path.exists(db_path):
        return JSONResponse({"error": "Database not found"}, status_code=404)
    
    # Create backup with _bak suffix (will overwrite existing backup)
    backup_path = db_path.replace(".db", "_bak.db")
    try:
        shutil.copy2(db_path, backup_path)
        print(f"Database backup created: {backup_path}")
    except Exception as e:
        return JSONResponse({"error": f"Failed to create backup: {str(e)}"}, status_code=500)
    
    # Purge all tables
    try:
        with db() as con:
            # Get all table names
            cursor = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
            )
            tables = [row[0] for row in cursor.fetchall()]
            
            # Delete all rows from each table
            for table in tables:
                con.execute(f"DELETE FROM {table};")
                print(f"Purged table: {table}")
            
            con.commit()
    except Exception as e:
        return JSONResponse({"error": f"Failed to purge database: {str(e)}"}, status_code=500)
    
    return {
        "success": True,
        "message": "Database purged successfully",
        "backup_path": backup_path
    }


@app.post("/api/clear-usb-storage")
async def clear_usb_storage():
    """Clear all contents of USB_STORAGE directory."""
    if not os.path.exists(USB_STORAGE):
        return JSONResponse({"error": "USB storage not found"}, status_code=404)
    
    # Clear all contents
    try:
        for filename in os.listdir(USB_STORAGE):
            file_path = os.path.join(USB_STORAGE, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                print(f"Removed: {file_path}")
            except Exception as e:
                print(f"Failed to remove {file_path}: {e}")
    except Exception as e:
        return JSONResponse({"error": f"Failed to clear USB storage: {str(e)}"}, status_code=500)
    
    return {
        "success": True,
        "message": "USB storage cleared successfully"
    }


@app.get("/api/system-status")
async def get_system_status():
    """Get current system status: disk space, memory, CPU, temperature, power draw."""
    try:
        # Get disk usage
        root_usage = shutil.disk_usage("/")
        usb_usage = None
        if os.path.exists(USB_STORAGE):
            usb_usage = shutil.disk_usage(USB_STORAGE)
        
        # Get memory usage
        memory = psutil.virtual_memory()
        
        # Get CPU usage
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # Get temperature (if available)
        temperature = None
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                # Try to get CPU temperature
                if 'coretemp' in temps:
                    temperature = temps['coretemp'][0].current
                elif 'acpitz' in temps:
                    temperature = temps['acpitz'][0].current
                elif len(temps) > 0:
                    temperature = list(temps.values())[0][0].current
        except Exception as e:
            print(f"Failed to get temperature: {e}")
        
        # Get power draw (if available)
        power_draw = None
        try:
            # Try to read power consumption from various sources
            with open('/sys/class/power_supply/BAT0/power_now', 'r') as f:
                power_uw = int(f.read().strip())
                power_draw = power_uw / 1000000  # Convert to watts
        except Exception:
            try:
                # Try alternative path
                with open('/sys/class/power_supply/BAT1/power_now', 'r') as f:
                    power_uw = int(f.read().strip())
                    power_draw = power_uw / 1000000
            except Exception:
                # Power draw not available on this system
                pass
        
        # Get database size
        database_size = 0
        try:
            if os.path.exists(DB_PATH):
                database_size = os.path.getsize(DB_PATH)
        except Exception as e:
            print(f"Failed to get database size: {e}")
        
        return {
            "timestamp": time.time(),
            "timestamp_str": datetime.now(timezone.utc).isoformat(),
            "disk": {
                "root": {
                    "total": root_usage.total,
                    "used": root_usage.used,
                    "free": root_usage.free,
                    "percent": root_usage.total > 0 and (root_usage.used / root_usage.total) * 100 or 0
                },
                "usb": {
                    "total": usb_usage.total if usb_usage else None,
                    "used": usb_usage.used if usb_usage else None,
                    "free": usb_usage.free if usb_usage else None,
                    "percent": usb_usage and (usb_usage.used / usb_usage.total) * 100 or None
                } if usb_usage else None
            },
            "memory": {
                "total": memory.total,
                "used": memory.used,
                "available": memory.available,
                "percent": memory.percent
            },
            "cpu": {
                "percent": cpu_percent
            },
            "temperature": temperature,
            "power_draw": power_draw,
            "database_size": database_size
        }
    except Exception as e:
        print(f"Error getting system status: {e}")
        return JSONResponse({"error": f"Failed to get system status: {str(e)}"}, status_code=500)



@app.post("/api/system/shutdown")
async def system_shutdown():
    """Shutdown the Raspberry Pi."""
    try:
        # Run shutdown command
        subprocess.Popen(['sudo', 'shutdown', '-h', 'now'], 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE)
        return {
            "success": True,
            "message": "System shutdown initiated"
        }
    except Exception as e:
        return JSONResponse({"error": f"Failed to shutdown: {str(e)}"}, status_code=500)


@app.post("/api/system/reboot")
async def system_reboot():
    """Reboot the Raspberry Pi."""
    try:
        # Run reboot command
        subprocess.Popen(['sudo', 'shutdown', '-r', '+0'], 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE)
        return {
            "success": True,
            "message": "System reboot initiated"
        }
    except Exception as e:
        return JSONResponse({"error": f"Failed to reboot: {str(e)}"}, status_code=500)


@app.post("/api/system/update")
async def system_update():
    """Update the SAR BT Scan system via git pull."""
    try:
        # Use explicit path to grpck's home directory to ensure correct location
        # even when running as root (not relying on ~ expansion)
        work_dir = "/home/grpck/sar_bt_scan/sar_bt_scan"
        
        # Check if directory exists
        if not os.path.exists(work_dir):
            return JSONResponse({"error": f"Directory not found: {work_dir}"}, status_code=404)
        
        # Run git pull as grpck user (not as root) to avoid permission issues
        # grpck is the owner of the directory
        result = subprocess.run(
            ['sudo', '-u', 'grpck', 'git', 'pull'],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Check if command was successful
        if result.returncode == 0:
            return {
                "success": True,
                "message": "Update completed successfully",
                "output": result.stdout,
                "status_code": result.returncode
            }
        else:
            return {
                "success": False,
                "message": "Update completed with errors",
                "output": result.stdout,
                "error": result.stderr,
                "status_code": result.returncode
            }
    except subprocess.TimeoutExpired:
        return JSONResponse({"error": "Update operation timed out"}, status_code=504)
    except Exception as e:
        return JSONResponse({"error": f"Failed to update: {str(e)}"}, status_code=500)


# ============= Confidence Analysis Endpoints =============

@app.get("/api/analyze/confidence/preview")
async def preview_confidence_analysis():
    """Preview confidence analysis without applying changes."""
    try:
        # Import analyzer module
        from confidence_analyzer import ConfidenceAnalyzer
        
        analyzer = ConfidenceAnalyzer()
        session, analyses = analyzer.analyze_all()
        
        if not session:
            return JSONResponse({"error": "No data to analyze"}, status_code=400)
        
        summary = analyzer.get_summary()
        
        # Add detailed device analysis for preview
        device_details = []
        for a in sorted(analyses, key=lambda x: -x.new_confidence):
            device_details.append({
                "mac": a.mac,
                "type": a.device_type,
                "old_confidence": a.old_confidence,
                "new_confidence": a.new_confidence,
                "sighting_count": a.sighting_count,
                "avg_rssi": round(a.avg_rssi, 1) if a.avg_rssi else None,
                "presence_ratio": round(a.presence_ratio * 100, 1),
                "factors": a.factors
            })
        
        summary["devices_detail"] = device_details
        summary["preview"] = True
        
        return summary
    except Exception as e:
        print(f"Error in confidence analysis preview: {e}")
        return JSONResponse({"error": f"Analysis failed: {str(e)}"}, status_code=500)


@app.post("/api/analyze/confidence")
async def run_confidence_analysis():
    """Run confidence analysis and update database."""
    try:
        # Import analyzer module
        from confidence_analyzer import ConfidenceAnalyzer
        
        analyzer = ConfidenceAnalyzer()
        session, analyses = analyzer.analyze_all()
        
        if not session:
            return JSONResponse({"error": "No data to analyze"}, status_code=400)
        
        # Apply updates
        result = analyzer.apply_updates()
        summary = analyzer.get_summary()
        summary["updates"] = result
        summary["applied"] = True
        
        return summary
    except Exception as e:
        print(f"Error in confidence analysis: {e}")
        return JSONResponse({"error": f"Analysis failed: {str(e)}"}, status_code=500)


@app.post("/api/oui/update")
async def update_oui_database():
    """Update the WiFi OUI vendor database from IEEE registry."""
    try:
        import subprocess
        import os
        
        # Get path to freeze_wifi_oui.py script
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script_path = os.path.join(script_dir, "freeze_wifi_oui.py")
        
        if not os.path.exists(script_path):
            return JSONResponse({"error": "OUI update script not found"}, status_code=404)
        
        # Run the script
        result = subprocess.run(
            ["python3", script_path],
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout
            cwd=script_dir
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            return JSONResponse({"error": f"Script failed: {error_msg}"}, status_code=500)
        
        # Parse output to get entry count
        entries = None
        for line in result.stdout.split('\n'):
            if 'OUI entries' in line:
                import re
                match = re.search(r'(\d+)\s*OUI entries', line)
                if match:
                    entries = int(match.group(1))
                    break
        
        return {
            "success": True,
            "message": "OUI database updated successfully",
            "entries": entries,
            "output": result.stdout
        }
    except subprocess.TimeoutExpired:
        return JSONResponse({"error": "OUI update timed out"}, status_code=504)
    except Exception as e:
        print(f"Error updating OUI database: {e}")
        return JSONResponse({"error": f"Update failed: {str(e)}"}, status_code=500)


def update_scanner_state(scan_mode: str, wifi_monitor_mode: bool):
    """Update scanner state (called from main.py)."""
    state.scanner_mode = scan_mode
    state.wifi_monitor_mode = wifi_monitor_mode
    state.last_update = time.time()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=WEB_UI_HOST, port=WEB_UI_PORT)
