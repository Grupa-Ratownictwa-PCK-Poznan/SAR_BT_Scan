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

# Source URLs - in priority order (earlier sources override later ones when conflicts occur)
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
    """Parse IEEE OUI CSV format into OUI->vendor mapping.
    
    Format: Registry,Assignment,Organization Name
    E.g.: MA-L,001A2B,PHYSICAL DEVICES INC
    """
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
    
    Format: 00:00:00  Vendor-Name
    or:     00:00:00/24 Vendor-Name (with mask)
    """
    mapping: dict[str, str] = {}
    
    for line in text.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # Split by whitespace
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        
        mac_part = parts[0]
        vendor = parts[1].strip()
        
        # Extract OUI (first 6 hex digits, handle both formats)
        # Format: 00:00:00 or 00:00:00/24
        oui = mac_part.split('/')[0].replace(':', '').upper()
        
        # Validate OUI format (6 hex chars)
        if not re.match(r'^[0-9A-F]{6}$', oui):
            continue
        
        # Normalize vendor name
        vendor = _normalize_name(vendor)
        if not vendor:
            continue
        
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
        
        # Split by whitespace
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        
        oui = parts[0].upper()
        vendor = parts[1].strip()
        
        # Validate OUI format (6 hex chars)
        if not re.match(r'^[0-9A-F]{6}$', oui):
            continue
        
        # Normalize vendor name
        vendor = _normalize_name(vendor)
        if not vendor:
            continue
        
        mapping[oui] = vendor
    
    return mapping


def merge_oui_sources(ieee_map: dict, wireshark_map: dict, arpscan_map: dict) -> tuple[dict, dict]:
    """Merge OUI mappings from multiple sources with priority.
    
    Priority: IEEE > Wireshark > ARP-scan
    
    Returns: (merged_mapping, source_counts)
    """
    merged = {}
    sources = {
        'ieee': 0,
        'wireshark': 0,
        'arpscan': 0,
    }
    
    # Start with IEEE (highest priority)
    merged.update(ieee_map)
    sources['ieee'] = len(ieee_map)
    
    # Add Wireshark entries not in IEEE
    for oui, vendor in wireshark_map.items():
        if oui not in merged:
            merged[oui] = vendor
            sources['wireshark'] += 1
    
    # Add ARP-scan entries not in IEEE or Wireshark
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
# Source of truth: Merged from IEEE MA-L Registry + Wireshark + ARP-scan
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
    
    print(f"Generated {output_path} with {len(mapping)} OUI entries")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate static WiFi OUI lookup file from IEEE registry",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python freeze_wifi_oui.py              # Generate wifi_oui_lookup.py
  python freeze_wifi_oui.py -o my_oui.py # Custom output path
  python freeze_wifi_oui.py --dry-run    # Preview without writing file
        """
    )
    
    parser.add_argument(
        "-o", "--output",
        default=OUTPUT_FILE,
        help=f"Output file path (default: {OUTPUT_FILE})"
    )
    
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview without writing file"
    )
    
    parser.add_argument(
        "--url",
        default=IEEE_OUI_URL,
        help=f"Source URL (default: {IEEE_OUI_URL})"
    )
    
    args = parser.parse_args()
    
    print(f"Fetching OUI data from {args.url}...")
    try:
        csv_data = _fetch(args.url)
    except Exception as e:
        print(f"ERROR: Failed to fetch OUI data: {e}")
        sys.exit(1)
    
    print("Parsing OUI entries...")
    mapping = _parse_ieee_csv(csv_data)
    
    if not mapping:
        print("ERROR: No valid OUI entries found")
        sys.exit(1)
    
    print(f"Found {len(mapping)} OUI entries")
    
    if args.dry_run:
        print(f"[DRY RUN] Would generate {args.output}")
        # Show sample entries
        print("\nSample entries:")
        for oui, vendor in list(mapping.items())[:10]:
            print(f"  {oui} -> {vendor}")
    else:
        # Resolve output path relative to script location
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(script_dir, args.output) if not os.path.isabs(args.output) else args.output
        
        generate_lookup_file(mapping, output_path)
        print(f"Successfully generated {output_path}")


if __name__ == "__main__":
    main()
