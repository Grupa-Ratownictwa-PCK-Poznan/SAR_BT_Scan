"""
GPS helper library for VK-162 (or any GPS feeding gpsd).

Requires:
  sudo apt install gpsd gpsd-clients python3-gps

This module provides:
  - init_gps(): start a gpsd client in a background thread
  - get_gps_status(): fix state & accuracy info
  - get_gps_time(): current UTC from GPS (datetime)
  - sync_system_time(): set system clock from GPS UTC (needs sudo)
  - get_location(): lat/lon/alt with timestamp and accuracy estimate

Usage example (in another script):
  import gps_client as gc
  gc.init_gps(wait_for_fix=True, timeout=20)
  print(gc.get_gps_status())
  print(gc.get_location())
  print(gc.get_gps_time())
  # gc.sync_system_time()  # requires sudo
"""
from __future__ import annotations

import math
import threading
import time
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any

try:
    from gps import gps, WATCH_ENABLE, WATCH_NEWSTYLE
    GPS_AVAILABLE = True
except Exception:
    GPS_AVAILABLE = False
    # Mock classes for when GPS is not available
    class gps:
        pass
    WATCH_ENABLE = 0
    WATCH_NEWSTYLE = 0


@dataclass
class GPSStatus:
    mode: int  # 0/1=no fix, 2=2D, 3=3D
    fix_ok: bool
    sats_used: Optional[int]
    hdop: Optional[float]
    vdop: Optional[float]
    pdop: Optional[float]
    epx: Optional[float]  # 1-sigma meters (east-west)
    epy: Optional[float]  # 1-sigma meters (north-south)
    epv: Optional[float]  # 1-sigma meters (vertical)
    last_update: Optional[datetime]


@dataclass
class GPSLocation:
    lat: float
    lon: float
    alt: Optional[float]
    timestamp_utc: Optional[datetime]
    accuracy_m_2d_cep95: Optional[float]


if GPS_AVAILABLE:
    class _GPSWorker:
        def __init__(self, host: str = "127.0.0.1", port: int = 2947):
            self._host = host
            self._port = port
            self._session = gps(host=host, port=port, mode=WATCH_ENABLE | WATCH_NEWSTYLE)
            self._session.sock.settimeout(5.0)
            self._lock = threading.Lock()
            self._stop = threading.Event()
            self._thread: Optional[threading.Thread] = None
            self._latest_tpv: Optional[Dict[str, Any]] = None
            self._latest_sky: Optional[Dict[str, Any]] = None
            self._last_update: Optional[datetime] = None

        def start(self) -> None:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run, name="gpsd-reader", daemon=True)
            self._thread.start()

        def stop(self) -> None:
            self._stop.set()
            if self._thread:
                self._thread.join(timeout=1.0)
            try:
                self._session.close()
            except Exception:
                pass

        def _run(self) -> None:
            while not self._stop.is_set():
                try:
                    for report in self._session:  # generator, blocks internally
                        if self._stop.is_set():
                            break
                        try:
                            cls = report.get("class") if hasattr(report, "get") else getattr(report, "class", None)
                            if cls == "TPV":
                                # extract only what we need
                                tpv = {
                                    "lat": getattr(report, "lat", None),
                                    "lon": getattr(report, "lon", None),
                                    "alt": getattr(report, "alt", None),
                                    "epx": getattr(report, "epx", None),
                                    "epy": getattr(report, "epy", None),
                                    "epv": getattr(report, "epv", None),
                                    "mode": getattr(report, "mode", 0),
                                    "time": getattr(report, "time", None),
                                    "speed": getattr(report, "speed", None),
                                    "track": getattr(report, "track", None),
                                    "sats": getattr(report, "satellites_used", None) if hasattr(report, "satellites_used") else None,
                                }
                                with self._lock:
                                    self._latest_tpv = tpv
                                    self._last_update = datetime.now(timezone.utc)
                            elif cls == "SKY":
                                sky = {
                                    "hdop": getattr(report, "hdop", None),
                                    "vdop": getattr(report, "vdop", None),
                                    "pdop": getattr(report, "pdop", None),
                                    "satellites": getattr(report, "satellites", None),  # list w/ PRNs & used flags
                                }
                                with self._lock:
                                    self._latest_sky = sky
                                    self._last_update = datetime.now(timezone.utc)
                        except Exception:
                            # swallow malformed frames; keep reading
                            continue
                except Exception:
                    # connection lost; reconnect with backoff
                    if self._stop.is_set():
                        break
                    time.sleep(1)
                    try:
                        self._session.close()
                    except Exception:
                        pass
                    try:
                        self._session = gps(host=self._host, port=self._port, mode=WATCH_ENABLE | WATCH_NEWSTYLE)
                        self._session.sock.settimeout(5.0)
                    except Exception:
                        pass

        def get_status(self) -> GPSStatus:
            with self._lock:
                tpv = self._latest_tpv or {}
                sky = self._latest_sky or {}
                mode = int(tpv.get("mode") or 0)
                fix_ok = mode >= 2
                # sats used: prefer TPV.satellites_used if available, else count SKY.satellites used==True
                sats_used = tpv.get("sats")
                if sats_used is None and isinstance(sky.get("satellites"), list):
                    try:
                        sats_used = sum(1 for s in sky["satellites"] if getattr(s, "used", False) or (isinstance(s, dict) and s.get("used")))
                    except Exception:
                        sats_used = None
                return GPSStatus(
                    mode=mode,
                    fix_ok=fix_ok,
                    sats_used=int(sats_used) if sats_used is not None else None,
                    hdop=_to_float(sky.get("hdop")),
                    vdop=_to_float(sky.get("vdop")),
                    pdop=_to_float(sky.get("pdop")),
                    epx=_to_float(tpv.get("epx")),
                    epy=_to_float(tpv.get("epy")),
                    epv=_to_float(tpv.get("epv")),
                    last_update=self._last_update,
                )

        def get_time(self) -> Optional[datetime]:
            with self._lock:
                tpv = self._latest_tpv
                iso = tpv.get("time") if tpv else None
            return _parse_iso_utc(iso)

        def get_location(self) -> Optional[GPSLocation]:
            with self._lock:
                tpv = self._latest_tpv or {}
                sky = self._latest_sky or {}
                lat = tpv.get("lat")
                lon = tpv.get("lon")
                alt = _to_float(tpv.get("alt"))
                epx = _to_float(tpv.get("epx"))
                epy = _to_float(tpv.get("epy"))
                iso = tpv.get("time")
            if lat is None or lon is None:
                return None
            return GPSLocation(
                lat=float(lat),
                lon=float(lon),
                alt=alt,
                timestamp_utc=_parse_iso_utc(iso),
                accuracy_m_2d_cep95=2.0 * (epx**2 + epy**2) ** 0.5 if (epx is not None and epy is not None) else None,
            )
else:
    # Mock _GPSWorker when GPS is not available
    class _GPSWorker:
        def __init__(self, *args, **kwargs):
            pass
        def start(self) -> None:
            pass
        def stop(self) -> None:
            pass
        def get_status(self) -> GPSStatus:
            return GPSStatus(mode=0, fix_ok=False, sats_used=None, hdop=None, vdop=None, pdop=None, epx=None, epy=None, epv=None, last_update=None)
        def get_time(self) -> Optional[datetime]:
            return None
        def get_location(self) -> Optional[GPSLocation]:
            return None

def _to_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        f = float(x)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except Exception:
        return None


# ---- Public API (module-level) -------------------------------------------------

_client: Optional[_GPSWorker] = None


def init_gps(host: str = "127.0.0.1", port: int = 2947, *, wait_for_fix: bool = False, timeout: float = 15.0) -> None:
    """Initialize gpsd client and start background reader.

    Args:
        host: gpsd host (default 127.0.0.1)
        port: gpsd port (default 2947)
        wait_for_fix: if True, block until we have at least 2D fix or timeout
        timeout: seconds to wait when wait_for_fix=True
    """
    global _client
    try:
        if _client is None:
            _client = _GPSWorker(host=host, port=port)
            _client.start()
        if wait_for_fix:
            _wait_until(lambda: (_client.get_status().fix_ok if _client else False), timeout)
    except Exception:
        # Gracefully fail if gpsd unavailable; scanner continues without GPS
        pass


def get_gps_status() -> Optional[GPSStatus]:
    """Return current GPS status (fix & accuracy). None if not initialized."""
    if _client is None:
        return None
    return _client.get_status()


def get_gps_time() -> Optional[datetime]:
    """Return current GPS UTC time (datetime, tz-aware) or None if unavailable."""
    if _client is None:
        return None
    return _client.get_time()


def sync_system_time() -> bool:
    """Set system clock from GPS UTC. Returns True on success.

    Requires privilege to set time (run script as root or with suitable capabilities).
    """
    if _client is None:
        return False
    dt = _client.get_time()
    if not dt:
        return False
    iso = dt.strftime("%Y-%m-%d %H:%M:%S")
    try:
        # Use `date -u -s` to avoid locale issues; set in UTC
        result = subprocess.run(["sudo", "date", "-u", "-s", iso], capture_output=True)
        return result.returncode == 0
    except Exception:
        return False


def get_location() -> Optional[GPSLocation]:
    """Return current location with timestamp & accuracy, or None if not available."""
    if _client is None:
        return None
    return _client.get_location()


# ---- helpers -------------------------------------------------------------------

def _wait_until(pred, timeout: float) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            if pred():
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False

def _parse_iso_utc(iso: Optional[str]) -> Optional[datetime]:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None

if __name__ == "__main__":
    # Simple self-test
    init_gps(wait_for_fix=False)
    time.sleep(2)
    print("Status:", get_gps_status())
    print("Time:", get_gps_time())
    print("Location:", get_location())



""" --------------- OTHER STUFF ------------------

# -------- systemd: GPS time sync helper (uses this library) ---------------------
# File: /usr/local/bin/gps_time_sync.py
# Purpose: wait for a 2D/3D fix via gpsd and set system time once.

#!/usr/bin/env python3
import sys
import time
import gps_client as gc

def main(timeout=60):
    gc.init_gps(wait_for_fix=True, timeout=timeout)
    if not gc.get_gps_time():
        # give gpsd a few extra seconds to populate time
        for _ in range(10):
            time.sleep(1)
            if gc.get_gps_time():
                break
    ok = gc.sync_system_time()
    if not ok:
        print("[gps_time_sync] Failed to sync system time from GPS.", file=sys.stderr)
        return 1
    status = gc.get_gps_status()
    print(f"[gps_time_sync] Time synced. mode={status.mode if status else '?'} fix_ok={status.fix_ok if status else False}")
    return 0

if __name__ == "__main__":
    t = 90
    if len(sys.argv) > 1:
        try:
            t = int(sys.argv[1])
        except Exception:
            pass
    raise SystemExit(main(timeout=t))


# -------- systemd unit: gps-time-sync.service -----------------------------------
# File: /etc/systemd/system/gps-time-sync.service
# Purpose: run once on boot to set system clock from GPS (requires sudo/root)

[Unit]
Description=Sync system clock from GPS via gpsd
Wants=gpsd.service
After=gpsd.service network-online.target

[Service]
Type=oneshot
# Wait until tty appears (VK-162 usually /dev/ttyACM0)
ExecStartPre=/bin/bash -c 'for i in {1..20}; do [ -e /dev/ttyACM0 ] && exit 0; sleep 1; done; exit 0'
# give gpsd a nudge to auto-open the port if socket-activated
ExecStartPre=/usr/bin/timeout 5s /usr/bin/cgps -s
ExecStart=/usr/bin/python3 /usr/local/bin/gps_time_sync.py 90
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target


# -------- gpsd config (option A: /etc/default/gpsd) ------------------------------
# Ensure gpsd opens VK-162 automatically with no client present
# File: /etc/default/gpsd
#
# START_DAEMON="true"
# GPSD_OPTIONS="-n"
# DEVICES="/dev/ttyACM0"
# USBAUTO="true"
# GPSD_SOCKET="/var/run/gpsd.sock"

# After editing:
#   sudo systemctl daemon-reload
#   sudo systemctl enable --now gpsd


# -------- gpsd config (option B: systemd drop-in) -------------------------------
# File: /etc/systemd/system/gpsd.service.d/override.conf
#
# [Service]
# ExecStart=
# ExecStart=/usr/sbin/gpsd -N -n -D 2 /dev/ttyACM0 -F /var/run/gpsd.sock
#
# Then:
#   sudo systemctl daemon-reload
#   sudo systemctl restart gpsd

END OTHER STUFF """
