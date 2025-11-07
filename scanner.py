#!/usr/bin/env python3
import argparse
import asyncio
import signal
import sys
import time
import subprocess
from typing import Dict, Any, Optional
import gps_client as gc
from settings import SCANNER_ID
from storage import init_db, db, upsert_device, add_sighting
from bt_manufacturer_ids import COMPANY_IDS

try:
    from bleak import BleakScanner
except ImportError:
    print("Error: bleak not installed. Use `sudo apt install python3-bleak` "
          "or a virtualenv: `python3 -m venv ~/bt-env && source ~/bt-env/bin/activate && pip install bleak`")
    sys.exit(1)

def _best_name(current: Optional[str], new: Optional[str]) -> Optional[str]:
    """Prefer the non-empty, longer, and more specific name."""
    candidates = [x for x in [new, current] if x]
    if not candidates:
        return current or new
    return max(candidates, key=len)


def detection_callback(device, advertisement_data):
    """
    Called on each advertisement.
    """

    scanner_id = SCANNER_ID

    best_name = advertisement_data.local_name or device.name
    device.address = device.address
    tx_power = advertisement_data.tx_power

    # Manufacturer data
    manufacturer = None
    manufacturer_hex = None
    company_hex = None # probably this or above only, should be the same!
    if advertisement_data.manufacturer_data:
        for m_id, m_bytes in advertisement_data.manufacturer_data.items():
            manufacturer = COMPANY_IDS.get(m_id, f"Unknown (0x{m_id:04X})")
            manufacturer_hex = m_bytes.hex()
            company_hex = f"0x{m_id:04X}"
            #print(f"  Raw data: {m_bytes.hex()}")

    # Service data (sometimes useful too)
    service = None
    if advertisement_data.service_data:
        for uuid, sdata in advertisement_data.service_data.items():
            #print(f"  Service {uuid}: {sdata.hex()}")
            service = uuid

    mac = device.address
    # Prefer rssi from advertisement_data if present, else device.rssi
    rssi = None
    if advertisement_data and getattr(advertisement_data, "rssi", None) is not None:
        rssi = advertisement_data.rssi
    elif getattr(device, "rssi", None) is not None:
        rssi = device.rssi

    now = time.time()
    gps_loc = gc.get_location()
    gps_time = gc.get_gps_time()

    # print(gc.get_gps_status())

    lat = None
    lon = None
    ts_gps = None

    if gps_loc is not None and hasattr(gps_loc, 'lat'):
        lat = gps_loc.lat
        lon = gps_loc.lon  

    if gps_time is not None:
        ts_gps = gps_time

    # add record to DB
    with db() as con:
        upsert_device(con,
                      addr=mac,
                      name=best_name,
                      manufacturer=manufacturer,
                      man_hex=company_hex,
                      now=now)

        add_sighting(con,
                     addr=mac,
                     ts_unix=now,
                     ts_gps=ts_gps,
                     lat=lat,
                     lon=lon,
                     #alt=gps_info.get("alt"),
                     #gps_hdop=gps_info.get("hdop"),
                     rssi=rssi,
                     tx_power=tx_power,
                     local_name=best_name,
                     manufacturer=manufacturer,
                     manufacturer_hex=company_hex,
                     service_uuid=service,
                     scanner=scanner_id,
                     adv_raw=None)  # can store advertisement_data.bytes if needed


    # print(f"Lat {lat}, Lon {lon}, TS_GPS {ts_gps}, Device {device.address}, RSSI={advertisement_data.rssi}, TX={tx_power}, Manufacturer {manufacturer}, Service {service}, Name {best_name}, Manufacturer HEX {company_hex}")



async def run(adapter: Optional[str], duration: Optional[float]):
    adapter_str = adapter if adapter is not None else "unknown"
    duration_str = str(duration) if duration is not None else "unspecified"
    #print(f"Initializing scanner with device {adapter_str} and duration of {duration_str} seconds.\n")

    # init GPS
    gc.init_gps(wait_for_fix=True, timeout=20)
    #print(gc.get_gps_status())
    #print(gc.get_location())
    #print(gc.get_gps_time())

    # end init GPS

    # init DB
    init_db()

    stop_event = asyncio.Event()

    def handle_sigint(*_):
        # Trigger graceful stop on Ctrl+C
        if not stop_event.is_set():
            stop_event.set()

    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, handle_sigint)
        except NotImplementedError:
            # Windows or restricted environments: ignore
            pass

    scanner_kwargs = {}
    if adapter:
        scanner_kwargs["adapter"] = adapter  # e.g., "hci1"

    scanner = BleakScanner(detection_callback, **scanner_kwargs)

    try:
        #adapter_ready(adapter)
        # Wait for BlueZ to be ready (up to ~5s)
        def adapter_ready(adapter: str) -> bool:
            try:
                out = subprocess.check_output(
                    ["bluetoothctl", "show"], input=f"select {adapter}\nshow\nquit\n".encode()
                ).decode(errors="ignore")
                return "Powered: yes" in out
            except Exception:
                return False

        for _ in range(10):
            if adapter is None or adapter_ready(adapter):
                break
            time.sleep(0.5)
        await scanner.start()
        if duration and duration > 0:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=duration)
            except asyncio.TimeoutError:
                pass
        else:
            await stop_event.wait()
    finally:
        await scanner.stop()
        # print_summary()
