#!/usr/bin/env python3
"""freeze_wifi_oui.py
---------------------------------
Generate a *static* Python file with WiFi OUI (Organizationally Unique Identifier)
to vendor mapping from multiple sources.

Output: wifi_oui_lookup.py with:
    OUI_VENDORS = { "AABBCC": "Apple, Inc.", ... }
    def lookup_vendor(mac: str) -> str: ...

Sources (in priority order):
  1. IEEE MA-L Registry (authoritative):
     https://standards-oui.ieee.org/oui/oui.csv
  
  2. Wireshark OUI database (more frequently updated):
     https://www.wireshark.org/download/automated/data/manuf
  
  3. ARP-scan mac-vendor database (community-maintained):
     https://raw.githubusercontent.com/royhills/arp-scan/master/ieee-oui.txt

Notes:
  * The output is *static*: no network at import time.
  * OUIs are stored as uppercase hex without delimiters (first 6 chars of MAC).
  * Vendor names are normalized for whitespace.
  * Multiple sources are merged with IEEE as primary source, filling gaps with others.
  * Backward compatible - same output format as original script.
"""
from __future__ import annotations
import argparse
import csv
import io
import os
import re
import sys
import time
import urllib.request
from datetime import datetime

IEEE_OUI_URL = "https://standards-oui.ieee.org/oui/oui.csv"
WIRESHARK_OUI_URL = "https://www.wireshark.org/download/automated/data/manuf"
ARPSCAN_OUI_URL = "https://raw.githubusercontent.com/royhills/arp-scan/master/ieee-oui.txt"

OUTPUT_FILE = "wifi_oui_lookup.py"


def _fetch(url: str, timeout: float = 60.0) -> str:
    """Fetch URL content."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "freeze-wifi-oui/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        return data.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  ⚠ Failed to fetch {url}: {e}")
        return ""


def _normalize_name(name: str) -> str:
    """Normalize vendor name."""
    name = re.sub(r"\s+", " ", name).strip()
    # Remove excessive trailing punctuation
    name = re.sub(r"[,.]$", "", name)
    return name


def _parse_ieee_csv(text: str) -> dict[str, str]:
    """Parse IEEE OUI CSV format into OUI->vendor mapping."""
    mapping: dict[str, str] = {}
    
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)  # Skip header row
    
    for row in reader:
        if len(row) < 3:
            continue
        
        registry = row[0].strip()  # MA-L, MA-M, MA-S
        oui = row[1].strip().upper()  # 6-char hex
        vendor = row[2].strip()
        
        # Only include MA-L (large block) entries - most common
        # MA-M and MA-S have different prefix lengths
        if registry != "MA-L":
            continue
        
        # Validate OUI format (6 hex chars)
        if not re.match(r'^[0-9A-F]{6}$', oui):
            continue
        
        # Normalize vendor name
        vendor = _normalize_name(vendor)
        if not vendor:
            vendor = "Unknown"
        
        mapping[oui] = vendor
    
    return mapping


def _parse_wireshark_manuf(text: str) -> dict[str, str]:
    """Parse Wireshark manuf file format into OUI->vendor mapping.
    
    Format: 00:00:00  Vendor-Name or 00:00:00/24 Vendor-Name
    """
    mapping: dict[str, str] = {}
    
    for line in text.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        
        mac_part = parts[0]
        vendor = parts[1].strip()
        oui = mac_part.split('/')[0].replace(':', '').upper()
        
        if not re.match(r'^[0-9A-F]{6}$', oui):
            continue
        
        vendor = _normalize_name(vendor)
        if vendor:
            mapping[oui] = vendor
    
    return mapping


def _parse_arpscan_oui(text: str) -> dict[str, str]:
    """Parse ARP-scan IEEE OUI format into OUI->vendor mapping.
    
    Format: 001A2B  Physical Devices Inc
    """
    mapping: dict[str, str] = {}
    
    for line in text.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        
        oui = parts[0].upper()
        vendor = parts[1].strip()
        
        if not re.match(r'^[0-9A-F]{6}$', oui):
            continue
        
        vendor = _normalize_name(vendor)
        if vendor:
            mapping[oui] = vendor
    
    return mapping


def merge_oui_sources(ieee_map: dict, wireshark_map: dict, arpscan_map: dict) -> tuple[dict, dict]:
    """Merge OUI mappings with priority: IEEE > Wireshark > ARP-scan"""
    merged = {}
    sources = {'ieee': 0, 'wireshark': 0, 'arpscan': 0}
    
    merged.update(ieee_map)
    sources['ieee'] = len(ieee_map)
    
    for oui, vendor in wireshark_map.items():
        if oui not in merged:
            merged[oui] = vendor
            sources['wireshark'] += 1
    
    for oui, vendor in arpscan_map.items():
        if oui not in merged:
            merged[oui] = vendor
            sources['arpscan'] += 1
    
    return merged, sources


def generate_lookup_file(mapping: dict[str, str], sources_info: dict, output_path: str) -> None:
    """Generate Python lookup file from OUI mapping."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    sources_text = "\n".join([
        f"#   - IEEE MA-L Registry: {sources_info['ieee']} entries",
        f"#   - Wireshark database: +{sources_info['wireshark']} new entries",
        f"#   - ARP-scan database: +{sources_info['arpscan']} new entries"
    ])
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f'''# Auto-generated on {timestamp} from multiple sources
# Source: Merged from IEEE MA-L Registry + Wireshark + ARP-scan
# https://standards-oui.ieee.org/
# https://www.wireshark.org/download/automated/data/manuf
# https://github.com/royhills/arp-scan
#
# Total entries: {len(mapping)}
# {sources_text}
# 
# Usage:
#   from wifi_oui_lookup import lookup_vendor, guess_device_type
#   vendor = lookup_vendor("AA:BB:CC:DD:EE:FF")  # Returns vendor name or ""
#   device_type = guess_device_type("AA:BB:CC:DD:EE:FF", vendor)  # Returns guessed type

OUI_VENDORS = {{
''')
        
        # Sort by OUI for consistent output
        for oui in sorted(mapping.keys()):
            vendor = mapping[oui]
            # Escape quotes in vendor names
            vendor_escaped = vendor.replace("\\", "\\\\").replace('"', '\\"')
            f.write(f'    "{oui}": "{vendor_escaped}",\n')
        
        f.write('''}

# Device type heuristics based on vendor patterns
_DEVICE_TYPE_PATTERNS = {
    # Smartphones
    "phone": [
        "Apple", "Samsung", "Huawei", "Xiaomi", "OnePlus", "Google", "Motorola",
        "Sony Mobile", "LG Electronics", "Nokia", "Honor", "Oppo", "Vivo", "Realme",
        "ZTE", "Alcatel", "HTC", "Asus", "Essential", "Razer Phone"
    ],
    # Laptops/Computers
    "computer": [
        "Dell", "HP Inc", "Hewlett Packard", "Lenovo", "Microsoft", "Acer",
        "ASUSTek", "Toshiba", "Fujitsu", "Panasonic", "Sony Corporation",
        "MSI", "Gigabyte", "Intel Corporate"
    ],
    # Wearables
    "wearable": [
        "Fitbit", "Garmin", "Polar", "Suunto", "Fossil", "Withings",
        "Amazfit", "Huami", "Coros", "Whoop"
    ],
    # IoT/Smart Home
    "iot": [
        "Espressif", "Tuya", "Shenzhen", "Amazon", "Ring", "Nest", "Ecobee",
        "Philips Lighting", "LIFX", "Sonoff", "TP-Link", "Netgear", "Arlo",
        "Wyze", "Eufy", "iRobot", "Roborock", "Dyson"
    ],
    # Network Equipment
    "network": [
        "Cisco", "Juniper", "Aruba", "Ubiquiti", "MikroTik", "Ruckus",
        "Extreme Networks", "Fortinet", "Palo Alto", "Meraki", "Arista",
        "D-Link", "Linksys", "NETGEAR", "Buffalo", "Zyxel"
    ],
    # Tablets
    "tablet": [
        "iPad", "Surface", "Galaxy Tab", "Fire Tablet", "Kindle"
    ],
    # Medical Devices
    "medical": [
        "Masimo", "Medtronic", "Philips Medical", "GE Healthcare",
        "Siemens Health", "Dexcom", "Abbott", "Omron"
    ],
    # Audio/Media
    "audio": [
        "Bose", "JBL", "Harman", "Bang & Olufsen", "Sennheiser", "Jabra",
        "Sonos", "Beats", "Audio-Technica", "Plantronics", "GN Audio"
    ],
}


def lookup_vendor(mac: str) -> str:
    """
    Look up vendor name from MAC address using OUI prefix.
    
    Args:
        mac: MAC address in any common format (AA:BB:CC:DD:EE:FF, 
             AA-BB-CC-DD-EE-FF, AABBCCDDEEFF)
    
    Returns:
        Vendor name string, or empty string if not found.
    """
    # Normalize MAC: remove delimiters, uppercase, take first 6 chars
    oui = mac.upper().replace(":", "").replace("-", "").replace(".", "")[:6]
    
    if len(oui) != 6:
        return ""
    
    return OUI_VENDORS.get(oui, "")


def guess_device_type(mac: str, vendor: str = None) -> str:
    """
    Guess device type based on vendor name patterns.
    
    This is heuristic-based and may not always be accurate.
    
    Args:
        mac: MAC address
        vendor: Vendor name (will be looked up if not provided)
    
    Returns:
        Guessed device type string, or empty string if unknown.
    """
    if vendor is None:
        vendor = lookup_vendor(mac)
    
    if not vendor:
        return ""
    
    vendor_lower = vendor.lower()
    
    # Check each device type pattern
    for device_type, patterns in _DEVICE_TYPE_PATTERNS.items():
        for pattern in patterns:
            if pattern.lower() in vendor_lower:
                return device_type
    
    # Additional heuristics based on vendor name patterns
    if "mobile" in vendor_lower or "wireless" in vendor_lower:
        return "mobile"
    
    if "camera" in vendor_lower:
        return "camera"
    
    if "tv" in vendor_lower or "television" in vendor_lower or "display" in vendor_lower:
        return "tv"
    
    if "printer" in vendor_lower or "printing" in vendor_lower:
        return "printer"
    
    if "automotive" in vendor_lower or "vehicle" in vendor_lower:
        return "automotive"
    
    return ""


def lookup_and_guess(mac: str) -> tuple[str, str]:
    """
    Convenience function to get both vendor and device type.
    
    Args:
        mac: MAC address
    
    Returns:
        Tuple of (vendor, device_type)
    """
    vendor = lookup_vendor(mac)
    device_type = guess_device_type(mac, vendor)
    return vendor, device_type
''')
    
    print(f"✓ Generated {output_path} with {len(mapping)} OUI entries")
    print(f"  - IEEE:      {sources_info['ieee']} entries")
    if sources_info['wireshark'] > 0:
        print(f"  - Wireshark: +{sources_info['wireshark']} new (gap-fill)")
    if sources_info['arpscan'] > 0:
        print(f"  - ARP-scan:  +{sources_info['arpscan']} new (gap-fill)")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate static WiFi OUI lookup file from multiple sources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python freeze_wifi_oui.py              # Generate from all sources (IEEE + Wireshark + ARP-scan)
  python freeze_wifi_oui.py --ieee-only  # Use only IEEE (original behavior)
  python freeze_wifi_oui.py -o custom.py # Custom output path
  python freeze_wifi_oui.py --dry-run    # Preview without writing
        """
    )
    
    parser.add_argument(
        "-o", "--output",
        default=OUTPUT_FILE,
        help=f"Output file (default: {OUTPUT_FILE})"
    )
    
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview without writing file"
    )
    
    parser.add_argument(
        "--ieee-only",
        action="store_true",
        help="Use only IEEE (original behavior)"
    )
    
    args = parser.parse_args()
    
    sources_info = {'ieee': 0, 'wireshark': 0, 'arpscan': 0}
    
    # Fetch IEEE (primary source)
    print(f"1. Fetching IEEE MA-L Registry...")
    ieee_data = _fetch(IEEE_OUI_URL)
    if ieee_data:
        ieee_mapping = _parse_ieee_csv(ieee_data)
        print(f"   ✓ Found {len(ieee_mapping)} IEEE entries")
    else:
        print("   ✗ Failed to fetch IEEE data")
        sys.exit(1)
    
    # Fetch other sources unless IEEE-only mode
    wireshark_mapping = {}
    arpscan_mapping = {}
    if not args.ieee_only:
        print(f"2. Fetching Wireshark database...")
        wireshark_data = _fetch(WIRESHARK_OUI_URL)
        if wireshark_data:
            wireshark_mapping = _parse_wireshark_manuf(wireshark_data)
            print(f"   ✓ Found {len(wireshark_mapping)} Wireshark entries")
        else:
            print("   ⚠ Failed to fetch Wireshark data (proceeding with IEEE)")
        
        print(f"3. Fetching ARP-scan database...")
        arpscan_data = _fetch(ARPSCAN_OUI_URL)
        if arpscan_data:
            arpscan_mapping = _parse_arpscan_oui(arpscan_data)
            print(f"   ✓ Found {len(arpscan_mapping)} ARP-scan entries")
        else:
            print("   ⚠ Failed to fetch ARP-scan data (proceeding with IEEE)")
    else:
        print("2. Skipping Wireshark (IEEE-only mode)")
        print("3. Skipping ARP-scan (IEEE-only mode)")
    
    # Merge databases
    print("\n4. Merging databases...")
    merged_mapping, sources_info = merge_oui_sources(ieee_mapping, wireshark_mapping, arpscan_mapping)
    print(f"   ✓ Total: {len(merged_mapping)} entries")
    print(f"     - IEEE: {sources_info['ieee']} entries")
    if sources_info['wireshark'] > 0:
        print(f"     - Wireshark: +{sources_info['wireshark']} new (gap-fill)")
    if sources_info['arpscan'] > 0:
        print(f"     - ARP-scan: +{sources_info['arpscan']} new (gap-fill)")
    
    if args.dry_run:
        print(f"\n[DRY RUN] Would generate {args.output}")
        print("\nSample entries:")
        for oui, vendor in list(merged_mapping.items())[:10]:
            print(f"  {oui} -> {vendor}")
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(script_dir, args.output) if not os.path.isabs(args.output) else args.output
        
        print(f"\n5. Writing {output_path}...")
        generate_lookup_file(merged_mapping, sources_info, output_path)
        print("✓ Successfully generated wifi_oui_lookup.py with hybrid sources")


if __name__ == "__main__":
    main()
