"""WiFi MAC address utilities for detecting and analyzing randomized MACs."""


def is_locally_administered_mac(mac_str: str) -> bool:
    """Check if MAC address has locally-administered bit set (randomized).
    
    Locally-administered MACs indicate the device is using MAC randomization.
    Bit 1 of the first octet: 0=universal, 1=locally administered.
    
    Args:
        mac_str: MAC address string (e.g., "AA:BB:CC:DD:EE:FF")
    
    Returns:
        True if MAC is locally administered (likely randomized)
    """
    try:
        first_octet = int(mac_str.split(":")[0], 16)
        return (first_octet & 0x02) != 0
    except Exception:
        return False


def lookup_randomized_mac_vendor(mac_str: str) -> tuple[str, bool]:
    """Attempt to identify vendor of a randomized MAC.
    
    Tries multiple de-randomization patterns since devices use different strategies:
    - Clear bit 1 (locally-administered bit)
    - Clear bits 0 and 1 (common pattern)
    - Toggle bit 1 (alternative pattern)
    
    If vendor is found via de-randomization, returns it with [rand] marker.
    If MAC is randomized but vendor cannot be recovered, returns "[randomized]".
    
    Args:
        mac_str: MAC address string (e.g., "AA:BB:CC:DD:EE:FF")
    
    Returns:
        Tuple of (vendor_name, is_randomized):
        - vendor_name: Vendor name with "[rand]" marker if de-randomized, 
                      "[randomized]" if randomized but unrecoverable, or ""
        - is_randomized: True if MAC is locally-administered (randomized)
    """
    try:
        from wifi_oui_lookup import lookup_vendor
        
        # First try direct lookup
        vendor = lookup_vendor(mac_str)
        if vendor:
            return vendor, False
        
        # If not found and MAC is locally-administered, try de-randomization
        if is_locally_administered_mac(mac_str):
            octets = mac_str.split(":")
            first_octet = int(octets[0], 16)
            
            # Try multiple de-randomization patterns
            patterns_to_try = [
                first_octet & ~0x02,      # Clear bit 1 (locally-administered)
                first_octet & ~0x03,      # Clear bits 0 and 1 (common pattern)
                first_octet ^ 0x02,       # Toggle bit 1 (alternative)
            ]
            
            for pattern_octet in patterns_to_try:
                test_mac = f"{pattern_octet:02x}:{':'.join(octets[1:])}".upper()
                vendor = lookup_vendor(test_mac)
                if vendor:
                    return f"{vendor} [rand]", True
            
            # If still not found but is randomized, mark as anonymized
            return "[randomized]", True
        
        return "", False
    except Exception:
        return "", False
