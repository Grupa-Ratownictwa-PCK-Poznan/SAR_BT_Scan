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
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import time
import threading
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from settings import WEB_UI_HOST, WEB_UI_PORT, WEB_UI_REFRESH_INTERVAL, DB_FILE, SD_STORAGE
from storage import db
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
                query = "SELECT * FROM devices ORDER BY last_seen DESC"
                cursor = con.execute(query)
                
                for row in cursor.fetchall():
                    addr, first_seen, last_seen, name, manufacturer_hex, manufacturer = row
                    
                    # Filter by MAC if specified
                    if "mac_filter" in filters and filters["mac_filter"].lower() not in addr.lower():
                        continue
                    
                    results.append({
                        "type": "device",
                        "mac": addr,
                        "name": name,
                        "manufacturer": manufacturer,
                        "manufacturer_hex": manufacturer_hex,
                        "first_seen": first_seen,
                        "last_seen": last_seen,
                        "last_seen_str": datetime.fromtimestamp(last_seen).isoformat()
                    })
            
            elif device_type == "wifi":
                query = "SELECT * FROM wifi_devices ORDER BY last_seen DESC"
                cursor = con.execute(query)
                
                for row in cursor.fetchall():
                    mac, first_seen, last_seen, vendor = row
                    
                    # Filter by MAC if specified
                    if "mac_filter" in filters and filters["mac_filter"].lower() not in mac.lower():
                        continue
                    
                    results.append({
                        "type": "device",
                        "mac": mac,
                        "vendor": vendor,
                        "first_seen": first_seen,
                        "last_seen": last_seen,
                        "last_seen_str": datetime.fromtimestamp(last_seen).isoformat()
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
                (id_, mac, ts_unix, ts_gps, lat, lon, alt, ssid, rssi, scanner_name) = row
                
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
                    "rssi": rssi,
                    "scanner": scanner_name
                })
    
    except Exception as e:
        print(f"Error querying WiFi associations: {e}")
    
    return results


# ============= API Endpoints =============

@app.get("/api/status")
async def get_status():
    """Get current scanner status: GPS fix, mode, uptime."""
    gps_status = gc.get_gps_status()
    gps_loc = gc.get_location()
    
    return {
        "timestamp": time.time(),
        "timestamp_str": datetime.now().isoformat(),
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
            "wifi_monitor_mode": state.wifi_monitor_mode
        }
    }


@app.get("/api/bt/devices")
async def get_bt_devices(limit: int = Query(100, ge=1, le=1000),
                        offset: int = Query(0, ge=0),
                        mac_filter: Optional[str] = None):
    """Get BT devices list."""
    filters = {}
    if mac_filter:
        filters["mac_filter"] = mac_filter
    
    devices = query_devices("bt", limit=limit, offset=offset, filters=filters)
    return {"devices": devices, "count": len(devices)}


@app.get("/api/bt/sightings")
async def get_bt_sightings(
    limit: int = Query(500, ge=1, le=2000),
    mac_filter: Optional[str] = None,
    rssi_min: Optional[int] = Query(None, ge=-100, le=0),
    rssi_max: Optional[int] = Query(None, ge=-100, le=0),
    hours_back: Optional[int] = Query(None, ge=0)
):
    """Get BT sightings with filters."""
    time_start = None
    if hours_back:
        time_start = time.time() - (hours_back * 3600)
    
    sightings = query_sightings(
        mac_filter=mac_filter,
        rssi_min=rssi_min,
        rssi_max=rssi_max,
        time_start=time_start,
        limit=limit
    )
    return {"sightings": sightings, "count": len(sightings)}


@app.get("/api/wifi/devices")
async def get_wifi_devices(limit: int = Query(100, ge=1, le=1000),
                          offset: int = Query(0, ge=0),
                          mac_filter: Optional[str] = None):
    """Get WiFi devices list."""
    filters = {}
    if mac_filter:
        filters["mac_filter"] = mac_filter
    
    devices = query_devices("wifi", limit=limit, offset=offset, filters=filters)
    return {"devices": devices, "count": len(devices)}


@app.get("/api/wifi/associations")
async def get_wifi_associations(
    limit: int = Query(500, ge=1, le=2000),
    mac_filter: Optional[str] = None,
    ssid_filter: Optional[str] = None,
    rssi_min: Optional[int] = Query(None, ge=-100, le=0),
    rssi_max: Optional[int] = Query(None, ge=-100, le=0),
    hours_back: Optional[int] = Query(None, ge=0)
):
    """Get WiFi association requests with filters."""
    time_start = None
    if hours_back:
        time_start = time.time() - (hours_back * 3600)
    
    associations = query_wifi_associations(
        mac_filter=mac_filter,
        ssid_filter=ssid_filter,
        rssi_min=rssi_min,
        rssi_max=rssi_max,
        time_start=time_start,
        limit=limit
    )
    return {"associations": associations, "count": len(associations)}


@app.get("/api/map/heatmap")
async def get_heatmap_data(
    data_type: str = Query("all", regex="^(bt|wifi|assoc|all)$"),
    hours_back: Optional[int] = Query(None, ge=0)
):
    """Get heatmap data (GPS coordinates with RSSI) for map visualization."""
    time_start = None
    if hours_back:
        time_start = time.time() - (hours_back * 3600)
    
    heatmap_points = []
    
    try:
        with db() as con:
            # BT sightings
            if data_type in ("bt", "all"):
                query = "SELECT lat, lon, rssi FROM sightings WHERE lat IS NOT NULL AND lon IS NOT NULL"
                params = []
                
                if time_start:
                    query += " AND ts_unix >= ?"
                    params.append(time_start)
                
                cursor = con.execute(query, params)
                for lat, lon, rssi in cursor.fetchall():
                    if lat and lon:
                        heatmap_points.append({
                            "lat": lat,
                            "lon": lon,
                            "rssi": rssi,
                            "type": "bt",
                            "intensity": max(0, min(1, (rssi + 100) / 100))  # Normalize RSSI to 0-1
                        })
            
            # WiFi associations
            if data_type in ("wifi", "assoc", "all"):
                query = "SELECT lat, lon, rssi FROM wifi_associations WHERE lat IS NOT NULL AND lon IS NOT NULL"
                params = []
                
                if time_start:
                    query += " AND ts_unix >= ?"
                    params.append(time_start)
                
                cursor = con.execute(query, params)
                for lat, lon, rssi in cursor.fetchall():
                    if lat and lon:
                        heatmap_points.append({
                            "lat": lat,
                            "lon": lon,
                            "rssi": rssi,
                            "type": "assoc",
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
    
    except WebSocketDisconnect:
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


def update_scanner_state(scan_mode: str, wifi_monitor_mode: bool):
    """Update scanner state (called from main.py)."""
    state.scanner_mode = scan_mode
    state.wifi_monitor_mode = wifi_monitor_mode
    state.last_update = time.time()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=WEB_UI_HOST, port=WEB_UI_PORT)
