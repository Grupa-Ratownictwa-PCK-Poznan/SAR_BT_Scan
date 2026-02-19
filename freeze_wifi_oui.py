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

IEEE_OUI_URL = "https://standards-oui.ieee.org/oui/oui.csv"  # MA-L (24-bit)
IEEE_MAM_URL = "https://standards-oui.ieee.org/oui28/mam.csv"  # MA-M (28-bit)
IEEE_MAS_URL = "https://standards-oui.ieee.org/oui36/oui36.csv"  # MA-S (36-bit)
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


def _parse_ieee_csv(text: str, registry_type: str) -> dict[str, str]:
    """Parse IEEE OUI CSV format into OUI->vendor mapping for a specific registry type.
    
    Args:
        text: CSV content
        registry_type: 'MA-L' (6 chars), 'MA-M' (7 chars), or 'MA-S' (9 chars)
    
    Returns:
        Dictionary mapping OUI prefix to vendor name
    """
    mapping: dict[str, str] = {}
    
    # Expected prefix lengths for validation
    prefix_lengths = {'MA-L': 6, 'MA-M': 7, 'MA-S': 9}
    expected_len = prefix_lengths.get(registry_type, 6)
    
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)  # Skip header row
    
    for row in reader:
        if len(row) < 3:
            continue
        
        registry = row[0].strip()  # MA-L, MA-M, or MA-S
        oui = row[1].strip().upper()  # hex prefix
        vendor = row[2].strip()
        
        # Only include entries matching expected registry type
        if registry != registry_type:
            continue
        
        # Validate prefix length matches expected
        if not re.match(f'^[0-9A-F]{{{expected_len}}}$', oui):
            continue
        
        # Normalize vendor name
        vendor = _normalize_name(vendor)
        if not vendor or vendor.lower() == 'private':
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


def merge_oui_sources(ieee_maps: tuple, wireshark_map: dict, arpscan_map: dict) -> tuple[dict, dict, dict, dict]:
    """Merge OUI mappings with priority: IEEE > Wireshark > ARP-scan
    
    Args:
        ieee_maps: Tuple of (ma_l, ma_m, ma_s) mappings from IEEE
        wireshark_map: MA-L only mappings from Wireshark
        arpscan_map: MA-L only mappings from ARP-scan
    
    Returns:
        Tuple of (ma_l_merged, ma_m, ma_s, sources_info)
    """
    ma_l_ieee, ma_m, ma_s = ieee_maps
    
    sources = {
        'ieee_mal': len(ma_l_ieee),
        'ieee_mam': len(ma_m),
        'ieee_mas': len(ma_s),
        'wireshark': 0,
        'arpscan': 0
    }
    
    # Start with IEEE MA-L as base for MA-L merged
    ma_l_merged = dict(ma_l_ieee)
    
    # Fill gaps with Wireshark (MA-L only)
    for oui, vendor in wireshark_map.items():
        if oui not in ma_l_merged:
            ma_l_merged[oui] = vendor
            sources['wireshark'] += 1
    
    # Fill remaining gaps with ARP-scan (MA-L only)
    for oui, vendor in arpscan_map.items():
        if oui not in ma_l_merged:
            ma_l_merged[oui] = vendor
            sources['arpscan'] += 1
    
    return ma_l_merged, ma_m, ma_s, sources


def generate_lookup_file(ma_l: dict, ma_m: dict, ma_s: dict, sources_info: dict, output_path: str) -> None:
    """Generate Python lookup file from OUI mappings (MA-L, MA-M, MA-S)."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    total = len(ma_l) + len(ma_m) + len(ma_s)
    
    sources_text = "\n".join([
        f"#   - IEEE MA-L Registry: {sources_info['ieee_mal']} entries (24-bit prefix)",
        f"#   - IEEE MA-M Registry: {sources_info['ieee_mam']} entries (28-bit prefix)",
        f"#   - IEEE MA-S Registry: {sources_info['ieee_mas']} entries (36-bit prefix)",
        f"#   - Wireshark database: +{sources_info['wireshark']} new MA-L entries",
        f"#   - ARP-scan database: +{sources_info['arpscan']} new MA-L entries"
    ])
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f'''# Auto-generated on {timestamp} from multiple sources (HYBRID)
# Source: IEEE MA-L + MA-M + MA-S Registries + Wireshark + ARP-scan
# https://standards-oui.ieee.org/
# https://www.wireshark.org/download/automated/data/manuf
# https://github.com/royhills/arp-scan
#
# Total entries: {total}
# {sources_text}
# 
# Hybrid lookup: Checks MA-S (36-bit) -> MA-M (28-bit) -> MA-L (24-bit)
# This ensures maximum device identification coverage.
#
# Usage:
#   from wifi_oui_lookup import lookup_vendor, guess_device_type
#   vendor = lookup_vendor("AA:BB:CC:DD:EE:FF")  # Returns vendor name or ""
#   device_type = guess_device_type("AA:BB:CC:DD:EE:FF", vendor)  # Returns guessed type

# MA-L: 24-bit prefix (6 hex chars) - standard OUI
OUI_VENDORS_MAL = {{
''')
        
        # Write MA-L entries
        for oui in sorted(ma_l.keys()):
            vendor = ma_l[oui]
            vendor_escaped = vendor.replace("\\", "\\\\").replace('"', '\\"')
            f.write(f'    "{oui}": "{vendor_escaped}",\n')
        
        f.write('''}

# MA-M: 28-bit prefix (7 hex chars) - medium block
OUI_VENDORS_MAM = {
''')
        
        # Write MA-M entries
        for oui in sorted(ma_m.keys()):
            vendor = ma_m[oui]
            vendor_escaped = vendor.replace("\\", "\\\\").replace('"', '\\"')
            f.write(f'    "{oui}": "{vendor_escaped}",\n')
        
        f.write('''}

# MA-S: 36-bit prefix (9 hex chars) - small block
OUI_VENDORS_MAS = {
''')
        
        # Write MA-S entries
        for oui in sorted(ma_s.keys()):
            vendor = ma_s[oui]
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
    Look up vendor name from MAC address using hybrid OUI prefix matching.
    
    Checks prefixes in order of specificity: MA-S (36-bit) -> MA-M (28-bit) -> MA-L (24-bit).
    This ensures the most specific match is returned for devices in smaller blocks.
    
    Args:
        mac: MAC address in any common format (AA:BB:CC:DD:EE:FF, 
             AA-BB-CC-DD-EE-FF, AABBCCDDEEFF)
    
    Returns:
        Vendor name string, or empty string if not found.
    """
    # Normalize MAC: remove delimiters, uppercase
    mac_clean = mac.upper().replace(":", "").replace("-", "").replace(".", "")
    
    if len(mac_clean) < 6:
        return ""
    
    # Check MA-S first (9 hex chars = 36-bit prefix) - most specific
    if len(mac_clean) >= 9:
        prefix_9 = mac_clean[:9]
        if prefix_9 in OUI_VENDORS_MAS:
            return OUI_VENDORS_MAS[prefix_9]
    
    # Check MA-M next (7 hex chars = 28-bit prefix)
    if len(mac_clean) >= 7:
        prefix_7 = mac_clean[:7]
        if prefix_7 in OUI_VENDORS_MAM:
            return OUI_VENDORS_MAM[prefix_7]
    
    # Finally check MA-L (6 hex chars = 24-bit prefix) - standard OUI
    prefix_6 = mac_clean[:6]
    return OUI_VENDORS_MAL.get(prefix_6, "")


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
    
    total = len(ma_l) + len(ma_m) + len(ma_s)
    print(f"✓ Generated {output_path} with {total} OUI entries (hybrid)")
    print(f"  - MA-L: {sources_info['ieee_mal']} entries (24-bit)")
    print(f"  - MA-M: {sources_info['ieee_mam']} entries (28-bit)")
    print(f"  - MA-S: {sources_info['ieee_mas']} entries (36-bit)")
    if sources_info['wireshark'] > 0:
        print(f"  - Wireshark: +{sources_info['wireshark']} new MA-L (gap-fill)")
    if sources_info['arpscan'] > 0:
        print(f"  - ARP-scan: +{sources_info['arpscan']} new MA-L (gap-fill)")


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
    
    # Fetch IEEE registries (primary source - separate files for MA-L, MA-M, MA-S)
    print(f"1. Fetching IEEE OUI Registries...")
    
    # MA-L (24-bit prefix) - main OUI registry
    print(f"   1a. Fetching MA-L (24-bit prefix)...")
    mal_data = _fetch(IEEE_OUI_URL)
    if mal_data:
        ma_l_ieee = _parse_ieee_csv(mal_data, 'MA-L')
        print(f"       ✓ Found {len(ma_l_ieee)} MA-L entries")
    else:
        print("       ✗ Failed to fetch IEEE MA-L data")
        sys.exit(1)
    
    # MA-M (28-bit prefix) - medium block
    print(f"   1b. Fetching MA-M (28-bit prefix)...")
    mam_data = _fetch(IEEE_MAM_URL)
    if mam_data:
        ma_m = _parse_ieee_csv(mam_data, 'MA-M')
        print(f"       ✓ Found {len(ma_m)} MA-M entries")
    else:
        print("       ⚠ Failed to fetch IEEE MA-M data (continuing without)")
        ma_m = {}
    
    # MA-S (36-bit prefix) - small block
    print(f"   1c. Fetching MA-S (36-bit prefix)...")
    mas_data = _fetch(IEEE_MAS_URL)
    if mas_data:
        ma_s = _parse_ieee_csv(mas_data, 'MA-S')
        print(f"       ✓ Found {len(ma_s)} MA-S entries")
    else:
        print("       ⚠ Failed to fetch IEEE MA-S data (continuing without)")
        ma_s = {}
    
    ieee_maps = (ma_l_ieee, ma_m, ma_s)
    
    # Fetch other sources unless IEEE-only mode (these only provide MA-L equivalent)
    wireshark_mapping = {}
    arpscan_mapping = {}
    if not args.ieee_only:
        print(f"2. Fetching Wireshark database...")
        wireshark_data = _fetch(WIRESHARK_OUI_URL)
        if wireshark_data:
            wireshark_mapping = _parse_wireshark_manuf(wireshark_data)
            print(f"   ✓ Found {len(wireshark_mapping)} Wireshark entries (MA-L equivalent)")
        else:
            print("   ⚠ Failed to fetch Wireshark data (proceeding with IEEE)")
        
        print(f"3. Fetching ARP-scan database...")
        arpscan_data = _fetch(ARPSCAN_OUI_URL)
        if arpscan_data:
            arpscan_mapping = _parse_arpscan_oui(arpscan_data)
            print(f"   ✓ Found {len(arpscan_mapping)} ARP-scan entries (MA-L equivalent)")
        else:
            print("   ⚠ Failed to fetch ARP-scan data (proceeding with IEEE)")
    else:
        print("2. Skipping Wireshark (IEEE-only mode)")
        print("3. Skipping ARP-scan (IEEE-only mode)")
    
    # Merge databases
    print("\n4. Merging databases (hybrid approach)...")
    ma_l_merged, ma_m_final, ma_s_final, sources_info = merge_oui_sources(ieee_maps, wireshark_mapping, arpscan_mapping)
    total = len(ma_l_merged) + len(ma_m_final) + len(ma_s_final)
    print(f"   ✓ Total: {total} entries")
    print(f"     - IEEE MA-L: {sources_info['ieee_mal']} entries")
    print(f"     - IEEE MA-M: {sources_info['ieee_mam']} entries")
    print(f"     - IEEE MA-S: {sources_info['ieee_mas']} entries")
    if sources_info['wireshark'] > 0:
        print(f"     - Wireshark: +{sources_info['wireshark']} new MA-L (gap-fill)")
    if sources_info['arpscan'] > 0:
        print(f"     - ARP-scan: +{sources_info['arpscan']} new MA-L (gap-fill)")
    
    if args.dry_run:
        print(f"\n[DRY RUN] Would generate {args.output}")
        print("\nSample MA-L entries:")
        for oui, vendor in list(ma_l_merged.items())[:5]:
            print(f"  {oui} -> {vendor}")
        if ma_m_final:
            print("\nSample MA-M entries:")
            for oui, vendor in list(ma_m_final.items())[:5]:
                print(f"  {oui} -> {vendor}")
        if ma_s_final:
            print("\nSample MA-S entries:")
            for oui, vendor in list(ma_s_final.items())[:5]:
                print(f"  {oui} -> {vendor}")
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(script_dir, args.output) if not os.path.isabs(args.output) else args.output
        
        print(f"\n5. Writing {output_path}...")
        generate_lookup_file(ma_l_merged, ma_m_final, ma_s_final, sources_info, output_path)
        print("✓ Successfully generated wifi_oui_lookup.py with HYBRID sources (MA-L + MA-M + MA-S)")


if __name__ == "__main__":
    main()
