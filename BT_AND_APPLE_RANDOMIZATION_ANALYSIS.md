# BT & Apple Device Randomization Analysis

## Question 1: Why Are BT Devices Showing "Almost Nothing"?

### Root Cause: **UI Display Issue** ✅ FIXED

**The Problem:**
- The BLE scanner DOES capture manufacturer data from BLE advertisements ✓
- The database stores it (both `manufacturer` and `manufacturer_hex` columns) ✓
- The web API returns it correctly ✓
- **BUT:** The HTML table was NOT displaying the manufacturer column

**Evidence:**
- `scanner.py` lines 44-47: Parses manufacturer from BLE advertisement data
- `storage.py`: `devices` table has `manufacturer` and `manufacturer_hex` columns
- `web_ui/app.py` line 116: Query selects and returns manufacturer field
- `web_ui/index.html` line 1540: Manufacturer was in HTML data attributes but hidden

**The Fix:**
Updated `web_ui/index.html` (lines 968-1003 and 1527-1557):
- Added "Manufacturer" column header to BT devices table
- Updated `updateBTDevicesTable()` function to render manufacturer in table cell
- Updated colspan from 5 to 6 for empty state message

**Result:**
BT devices table now displays: MAC Address | Name | **Manufacturer** | Confidence | Last Seen | Notes

---

## Question 2: Will WiFi De-randomization Work on Apple Devices?

### Answer: **YES** ✅ With Caveats

### How Apple MAC Randomization Works

**WiFi (802.11):**
- Apple devices DO use MAC randomization on WiFi
- Pattern: **Keeps original OUI** (first 3 octets) but sets locally-administered bit
- Example: Real Apple MAC = `A0:10:F9:XX:XX:XX`
  - Randomized becomes = `A2:10:F9:RR:RR:RR` (bit 1 of first octet set)
- Your de-randomization logic detects this pattern ✓

**BLE (Bluetooth):**
- Uses **different randomization** than WiFi
- Uses RPA (Resolvable Private Address) format
- Bits 47:46 = "01" for RPA addresses
- Manufacturer info encoded in BLE advertisement, NOT in MAC
- MAC itself becomes mostly random

### De-randomization Compatibility

**WiFi:**
```
Your logic:
  first_octet = 0xA2  (randomized)
  is_locally_admin = (0xA2 & 0x02) != 0  → TRUE ✓
  Clear bit 1:
    0xA2 & ~0x02 = 0xA0  → Recover as "Apple [rand]" ✓
```

**Works for Apple because:**
- ✓ Apple keeps the OUI pattern
- ✓ Apple uses the same locally-administered bit pattern
- ✓ Apple OUI is likely in your `wifi_oui_lookup.py` database

### What Might Not Work

- **Full random MAC:** Some devices use completely random MACs (not just OUI + locally-admin bit)
  - Apple doesn't do this, so no problem
- **Future changes:** If Apple changes strategy, patterns may differ
- **Non-standard implementations:** Some Apple-compatible devices may behave differently

### Why No Apple Devices in Your Sample?

Based on your earlier data (95.8% of unmapped devices are randomized), possible reasons:
1. **Coverage area:** Fewer Apple devices broadcasting in your scanning range
2. **Privacy settings:** Apple may disable certain beacon types in certain contexts
3. **Network filters:** Some networks may filter Apple traffic
4. **Geographic/demographic:** Apple device density varies by region

---

## Summary: What Gets De-randomized?

### WiFi Devices ✅
- **Works:** Devices keeping OUI + setting locally-admin bit
- **Examples:** TP-LINK `84:D8:1B` → `8A:D8:1B`, Apple `A0:10:F9` → `A2:10:F9`, Ubiquiti
- **Marker:** Will show as `"Vendor [rand]"` in UI
- **Includes:** Apple devices (if in range)
- **Fails on:** Fully randomized MACs (different OUI than real device)

### BLE Devices ❌
- **Cannot recover vendor from randomized MAC** because:
  - MAC is fully random (doesn't encode OUI for BLE)
  - Manufacturer info is in advertisement data, not MAC address
  - Already captured separately in database
- **What works:** See `manufacturer` and `manufacturer_hex` in BT devices table ✓

---

## Next Steps (Optional Enhancements)

1. **Extend to BT:** Could add randomization detection for BLE RPA addresses
   - Would need separate logic (not OUI-based)
   - Would flag RPA usage but couldn't recover vendor name
   
2. **Track Apple Statistics:** Count Apple devices captured
   - Monitor effectiveness of de-randomization feature
   - Refine patterns if needed

3. **Add Hint System:** For unmapped BLE devices
   - Show if device uses RPA (random BLE address)
   - vs public address (non-randomized BLE)
