import argparse
import asyncio
import signal
import sys
import os
import time
import subprocess

from settings import USB_STORAGE, SD_STORAGE, BLEAK_DEVICE, SCAN_MODE, WIFI_INTERFACE, SCANNER_ID
from scanner import run as run_bt
import wifi_scanner as ws
import gps_client as gc
from storage import init_db

def main():
    # Main logic of the program goes here
    print("\n" + "="*60)
    print("SAR BT+WiFi Scanner")
    print("="*60)
    print(f"Scan Mode: {SCAN_MODE}")
    print(f"Scanner ID: {SCANNER_ID}")
    print(f"USB storage: {USB_STORAGE}")
    print(f"SD storage: {SD_STORAGE}")
    if SCAN_MODE in ("bt", "both"):
        print(f"BT device: {BLEAK_DEVICE}")
    if SCAN_MODE in ("wifi", "both"):
        print(f"WiFi interface: {WIFI_INTERFACE}")
    print("="*60 + "\n")

    os.environ["BLEAK_DEVICE"] = BLEAK_DEVICE
    
    # Initialize GPS (common for both)
    print("Initializing GPS...")
    gc.init_gps(wait_for_fix=False)
    time.sleep(1)
    gps_status = gc.get_gps_status()
    if gps_status and gps_status.fix_ok:
        print(f"✓ GPS: {gps_status.sats_used} satellites, HDOP={gps_status.hdop}")
    else:
        print("⚠ GPS: No fix yet (will continue without GPS)")
    
    # Initialize database
    print("Initializing database...")
    init_db()

    try:
        if SCAN_MODE == "bt":
            print("Starting BT scanner only...")
            asyncio.run(run_bt(None, None))
        elif SCAN_MODE == "wifi":
            print("Starting WiFi scanner only...")
            ws.start_wifi_scan(WIFI_INTERFACE, SCANNER_ID)
            # Keep running
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
            finally:
                ws.stop_wifi_scan()
        elif SCAN_MODE == "both":
            print("Starting BT and WiFi scanners...")
            ws.start_wifi_scan(WIFI_INTERFACE, SCANNER_ID)
            try:
                asyncio.run(run_bt(None, None))
            except KeyboardInterrupt:
                pass
            finally:
                ws.stop_wifi_scan()
        else:
            print(f"Error: Invalid SCAN_MODE '{SCAN_MODE}'. Use 'bt', 'wifi', or 'both'")
            sys.exit(1)
    except KeyboardInterrupt:
        # Fallback (some platforms)
        print("\nShutdown signal received...")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
