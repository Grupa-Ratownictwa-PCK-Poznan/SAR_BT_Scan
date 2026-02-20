import argparse
import asyncio
import signal
import sys
import os
import time
import subprocess
import threading

from settings import USB_STORAGE, SD_STORAGE, BLEAK_DEVICE, SCAN_MODE, WIFI_INTERFACE, SCANNER_ID
from settings import WEB_UI_ENABLED, WEB_UI_PORT, WEB_UI_HOST
try:
    from settings import BLE_PUBLISH_ENABLED, BLE_PUBLISH_INTERFACE
except ImportError:
    BLE_PUBLISH_ENABLED = False
    BLE_PUBLISH_INTERFACE = "hci0"
from scanner import run as run_bt
import wifi_scanner as ws
import gps_client as gc
from storage import init_db

def _sync_gps_time():
    """Background thread: continuously sync system time from GPS when available.
    
    Non-blocking: starts immediately and retries periodically with exponential backoff.
    Keeps trying even if GPS time isn't available at startup.
    """
    attempt = 0
    synced = False
    
    while not synced:
        gps_time = gc.get_gps_time()
        if gps_time:
            # Try to sync system time
            if gc.sync_system_time():
                print(f"✓ System time synced from GPS: {gps_time}")
                synced = True
            else:
                print("⚠ Failed to sync system time (may need root privileges)")
                synced = True  # Don't keep retrying if sync fails
        else:
            # GPS time not available yet, retry with backoff
            attempt += 1
            if attempt <= 5:
                # Quick retries: every 1 second for first 5 attempts
                sleep_time = 1
            elif attempt <= 20:
                # Medium retries: every 5 seconds for next 15 attempts (~1 min total)
                sleep_time = 5
            else:
                # Long retries: every 30 seconds indefinitely
                sleep_time = 30
            
            if attempt == 1:
                print("⏳ Waiting for GPS time...")
            elif attempt in (6, 21):
                print(f"⏳ Still waiting for GPS time (attempt {attempt})...")
            
            time.sleep(sleep_time)

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
    
    # Start background thread to sync system time from GPS ASAP
    time_sync_thread = threading.Thread(target=_sync_gps_time, daemon=True, name="gps-time-sync")
    time_sync_thread.start()
    
    gps_status = gc.get_gps_status()
    if gps_status and gps_status.fix_ok:
        print(f"✓ GPS: {gps_status.sats_used} satellites, HDOP={gps_status.hdop}")
    else:
        print("⚠ GPS: No fix yet (will continue without GPS)")
    
    # Initialize database
    print("Initializing database...")
    init_db()

    # Start Web UI if enabled
    if WEB_UI_ENABLED:
        print(f"\nStarting Web UI...")
        try:
            from web_ui.app import app, update_scanner_state
            import uvicorn
            
            # Update scanner state (WiFi monitor is ON if SCAN_MODE is wifi or both)
            wifi_monitor_active = SCAN_MODE in ("wifi", "both")
            update_scanner_state(SCAN_MODE, wifi_monitor_active)
            
            # Start web server in a background thread
            web_thread = threading.Thread(
                target=lambda: uvicorn.run(app, host=WEB_UI_HOST, port=WEB_UI_PORT, log_level="warning"),
                daemon=True,
                name="web-ui-server"
            )
            web_thread.start()
            
            print(f"✓ Web UI started at http://localhost:{WEB_UI_PORT}")
            time.sleep(1)  # Give the server time to start
        except ImportError as e:
            print("⚠ Web UI dependencies not installed (fastapi, uvicorn). Skipping.")
            print(f"  Error: {e}")
            print("  Install with: pip install fastapi uvicorn")
        except Exception as e:
            print(f"⚠ Failed to start Web UI: {e}")
    else:
        print("⚠ Web UI is disabled in settings")

    # Start BLE GATT Publisher if enabled (uses hci0, independent of scanner)
    if BLE_PUBLISH_ENABLED:
        print(f"\nStarting BLE GATT Publisher on {BLE_PUBLISH_INTERFACE}...")
        try:
            from ble_publisher import BLEGATTPublisher
            ble_publisher = BLEGATTPublisher(interface=BLE_PUBLISH_INTERFACE)
            ble_thread = threading.Thread(
                target=ble_publisher.run,
                daemon=True,
                name="ble-publisher"
            )
            ble_thread.start()
            print(f"✓ BLE Publisher started (advertising as SAR-Scanner)")
            time.sleep(1)  # Give the server time to start
        except ImportError as e:
            print(f"⚠ BLE Publisher dependencies not installed: {e}")
            print("  Install with: sudo apt install python3-dbus python3-gi")
        except Exception as e:
            print(f"⚠ Failed to start BLE Publisher: {e}")
    else:
        print("⚠ BLE Publisher is disabled in settings")

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
