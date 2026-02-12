#!/usr/bin/env python3
"""
WiFi scanner module for capturing association requests.

Captures 802.11 probe requests/association attempts from WiFi devices
in monitor mode. Extracts device MAC, SSID, and signal strength.

Requires:
  - USB WiFi adapter in monitor mode
  - scapy: pip install scapy
  - tcpdump (usually pre-installed)

Usage:
  import wifi_scanner as ws
  ws.start_wifi_scan(interface="wlan0")
  ws.stop_wifi_scan()
"""

import os
import sys
import signal
import threading
import time
from typing import Optional, Callable, Dict, Any

import gps_client as gc
from storage import db, upsert_wifi_device, add_wifi_association
from settings import KNOWN_WIFIS

try:
    from scapy.all import sniff, Dot11, Dot11Elt, conf
    from scapy.arch import get_if_hwaddr
except ImportError:
    print("Error: scapy not installed. Install with: pip install scapy")
    sys.exit(1)


class _WiFiScanner:
    def __init__(self, interface: str, scanner_name: str = "WiFi Scanner"):
        self.interface = interface
        self.scanner_name = scanner_name
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._packet_count = 0
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start capturing WiFi packets in background thread."""
        if self._thread and self._thread.is_alive():
            return
        
        # Verify interface exists and is in monitor mode
        if not self._check_interface():
            print(f"Error: Interface {self.interface} not ready or not in monitor mode")
            return
        
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="wifi-scanner", daemon=True)
        self._thread.start()
        print(f"WiFi scanner started on {self.interface}")

    def stop(self) -> None:
        """Stop the scanner thread."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        print(f"WiFi scanner stopped. Captured {self._packet_count} packets.")

    def _check_interface(self) -> bool:
        """Check if interface exists and is valid."""
        try:
            # Try to get hardware address - if successful, interface exists
            get_if_hwaddr(self.interface)
            return True
        except Exception:
            return False

    def _run(self) -> None:
        """Main packet capture loop."""
        try:
            # Suppress verbose scapy output
            conf.verb = 0
            
            # Start sniffing
            sniff(
                iface=self.interface,
                prn=self._packet_callback,
                stop_filter=lambda x: self._stop.is_set(),
                store=False,
                monitor=True,
            )
        except PermissionError:
            print(f"Error: Need root/sudo to capture on {self.interface}")
        except Exception as e:
            print(f"WiFi scanner error: {e}")

    def _packet_callback(self, pkt) -> None:
        """Process captured packet."""
        if self._stop.is_set():
            return
        
        try:
            # Only process packets with Dot11 (802.11) layer
            if not pkt.haslayer(Dot11):
                return
            
            # Get packet info
            mac = pkt.addr2  # Source MAC (client)
            if not mac or mac == "ff:ff:ff:ff:ff:ff":
                return
            
            # Parse SSID and other info from probe/assoc requests
            ssid = None
            signal_strength = None
            
            # Extract SSID from Dot11Elt (information elements)
            if pkt.haslayer(Dot11Elt):
                for elt in pkt[Dot11Elt]:
                    if elt.ID == 0:  # SSID information element
                        try:
                            ssid = elt.info.decode("utf-8", errors="ignore")
                            if not ssid:  # Hidden SSID
                                ssid = "<hidden>"
                        except Exception:
                            ssid = "<hidden>"
                    elif elt.ID == 3:  # Channel
                        pass
            
            # Skip if no SSID found and not a broadcast
            if not ssid:
                return
            
            # Filter by known SSIDs if configured
            if KNOWN_WIFIS and ssid != "<hidden>" and ssid not in KNOWN_WIFIS:
                return
            
            # Get signal strength (dBm)
            signal_strength = pkt.dBm_AntSignal if hasattr(pkt, "dBm_AntSignal") else None
            
            # Get GPS data
            now = time.time()
            gps_loc = gc.get_location()
            gps_time = gc.get_gps_time()
            
            lat = gps_loc.lat if gps_loc else None
            lon = gps_loc.lon if gps_loc else None
            alt = gps_loc.alt if gps_loc else None
            ts_gps = gps_time
            
            # Store in database
            with db() as con:
                upsert_wifi_device(con, mac, now=int(now))
                add_wifi_association(
                    con,
                    mac=mac,
                    ssid=ssid,
                    ts_unix=int(now),
                    ts_gps=ts_gps,
                    lat=lat,
                    lon=lon,
                    alt=alt,
                    rssi=signal_strength,
                    scanner=self.scanner_name,
                )
            
            # Console output
            with self._lock:
                self._packet_count += 1
                print(f"[WiFi] {mac} -> {ssid} (RSSI: {signal_strength})")
        
        except Exception as e:
            # Silently continue on malformed packets
            pass


# Module-level instance
_scanner: Optional[_WiFiScanner] = None


def start_wifi_scan(interface: str, scanner_name: str = "WiFi Scanner") -> None:
    """Start WiFi scanning on the given interface.
    
    Args:
        interface: Network interface in monitor mode (e.g., 'wlan0')
        scanner_name: Name identifier for this scanner
    """
    global _scanner
    if _scanner is None:
        _scanner = _WiFiScanner(interface, scanner_name)
    _scanner.start()


def stop_wifi_scan() -> None:
    """Stop the WiFi scanner."""
    global _scanner
    if _scanner:
        _scanner.stop()


def get_wifi_status() -> Dict[str, Any]:
    """Get current WiFi scanner status."""
    if _scanner is None:
        return {"status": "not_initialized", "packet_count": 0}
    return {
        "status": "running" if _scanner._thread and _scanner._thread.is_alive() else "stopped",
        "interface": _scanner.interface,
        "packet_count": _scanner._packet_count,
    }


if __name__ == "__main__":
    print("WiFi Scanner Module. Use start_wifi_scan() to activate.")
