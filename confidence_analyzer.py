#!/usr/bin/env python3
"""
Confidence Analyzer Module for SAR Scanner

This module analyzes device sighting patterns to estimate how likely a device
belongs to a missing person vs SAR team equipment.

Confidence scale: 0-100
  - 0: Almost certainly SAR team equipment (seen constantly, HQ equipment)
  - 50: Unknown/neutral (default)
  - 100: High probability of missing person's device

Factors that DECREASE confidence (likely SAR team):
  - Device seen throughout entire scanning session (high presence ratio)
  - Strong RSSI at both session start AND end (likely HQ equipment)
  - Very high sighting frequency (device always present)
  - Device seen by all scanners consistently

Factors that INCREASE confidence (possibly missing person):
  - Device appears only mid-session (not at boundaries)
  - Sporadic/clustered sightings
  - Single location appearance then gone
  - Low overall sighting count relative to session length

Usage:
  CLI:  python confidence_analyzer.py [--dry-run]
  API:  POST /api/analyze/confidence (from web UI)
"""

import sqlite3
import argparse
import sys
import os
import math
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field

# Import settings for database path and analyzer config
from settings import (
    SD_STORAGE, DB_FILE,
    HQ_LATITUDE, HQ_LONGITUDE, HQ_RADIUS_METERS,
    DEVICE_WHITELIST_FILE, SESSION_GAP_SECONDS
)

# Import WiFi OUI lookup for vendor/device type enrichment
try:
    from wifi_oui_lookup import lookup_vendor, guess_device_type, lookup_and_guess
    OUI_LOOKUP_AVAILABLE = True
except ImportError:
    OUI_LOOKUP_AVAILABLE = False
    print("Warning: wifi_oui_lookup not available. Run freeze_wifi_oui.py to generate.")
    def lookup_vendor(mac): return ""
    def guess_device_type(mac, vendor=None): return ""
    def lookup_and_guess(mac): return ("", "")

# Import MAC randomization utilities
try:
    from web_ui.mac_utils import is_locally_administered_mac
    MAC_UTILS_AVAILABLE = True
except ImportError:
    MAC_UTILS_AVAILABLE = False
    def is_locally_administered_mac(mac): return False

# Import device type classifier (expanded analysis)
try:
    from device_type_classifier import classify_device
    CLASSIFIER_AVAILABLE = True
except Exception:
    CLASSIFIER_AVAILABLE = False
    def classify_device(**kwargs): return ""

# Database path resolution (same logic as storage.py)
DB_PATH = SD_STORAGE + DB_FILE
if not os.path.exists(DB_PATH):
    if os.path.exists('/tmp/test_results.db'):
        DB_PATH = '/tmp/test_results.db'
    elif os.path.exists('./test_results.db'):
        DB_PATH = './test_results.db'


@dataclass
class SessionStats:
    """Overall session statistics."""
    start_time: int
    end_time: int
    duration: int
    total_bt_sightings: int
    total_wifi_associations: int
    total_bt_devices: int
    total_wifi_devices: int


@dataclass
class DeviceAnalysis:
    """Analysis results for a single device."""
    mac: str
    device_type: str  # "bt" or "wifi"
    first_seen: int
    last_seen: int
    sighting_count: int
    avg_rssi: Optional[float]
    presence_ratio: float
    early_presence: bool  # Present in first 10% of session
    late_presence: bool   # Present in last 10% of session
    early_rssi: Optional[float]  # Avg RSSI in first 10%
    late_rssi: Optional[float]   # Avg RSSI in last 10%
    old_confidence: int
    new_confidence: int
    factors: List[str]  # Explanation of scoring factors
    # GPS clustering fields
    hq_ratio: Optional[float] = None  # Ratio of sightings near HQ
    avg_distance_from_hq: Optional[float] = None  # Meters
    # OUI-based enrichment (WiFi only)
    vendor_name: Optional[str] = None  # From OUI lookup
    guessed_type: Optional[str] = None  # Heuristic device type guess
    # Multi-session fields
    session_count: int = 1  # Number of distinct sessions
    whitelisted: bool = False  # Is this a known SAR device
    # --- Enhanced analysis fields (v2) ---
    # RSSI trend analysis
    rssi_std_dev: Optional[float] = None  # Standard deviation of RSSI values
    rssi_has_peak: bool = False  # Rise-then-fall pattern detected
    # WiFi-specific analysis
    ssid_count: int = 0  # Number of unique SSIDs probed
    ssid_list: List[str] = field(default_factory=list)  # SSIDs probed
    is_beacon_device: Optional[bool] = None  # True=AP, False=client, None=BT/unknown
    # MAC analysis
    is_randomized_mac: bool = False  # Locally-administered MAC (randomized)
    # BT device identification
    device_name: Optional[str] = None  # BLE advertised name
    manufacturer_name: Optional[str] = None  # BLE manufacturer
    # Temporal analysis
    burstiness_cov: Optional[float] = None  # CoV of inter-sighting intervals
    active_presence_ratio: Optional[float] = None  # Time-bucketed presence ratio
    # Spatial analysis
    gps_spread_meters: Optional[float] = None  # Mean distance from GPS centroid
    # Multi-scanner
    scanner_count: int = 1  # Number of distinct scanners that saw this device
    # SAR role classification
    sar_role: Optional[str] = None  # "SAR HQ", "SAR TEAM", or None


class ConfidenceAnalyzer:
    """Analyzes device patterns and calculates confidence scores."""
    
    # Thresholds for analysis
    BOUNDARY_PERCENT = 0.10  # First/last 10% of session
    STRONG_RSSI_THRESHOLD = -60  # dBm, signals stronger than this are "strong"
    HIGH_PRESENCE_RATIO = 0.80  # Device present for >80% of session
    MEDIUM_PRESENCE_RATIO = 0.50  # Device present for >50% of session
    HIGH_SIGHTING_RATE = 0.70  # Sighting rate relative to expected
    
    # GPS clustering thresholds
    HQ_RATIO_HIGH = 0.90  # >90% sightings near HQ = very likely SAR team
    HQ_RATIO_LOW = 0.20   # <20% sightings near HQ = likely in field
    
    # RSSI trend thresholds
    RSSI_HIGH_VARIANCE_THRESHOLD = 10.0  # σ > 10 dBm = moving device
    RSSI_LOW_VARIANCE_THRESHOLD = 3.0    # σ < 3 dBm = stationary device
    RSSI_PEAK_MIN_DELTA = 3.0            # Min dBm difference for peak detection
    
    # Burstiness thresholds
    HIGH_BURSTINESS_COV = 1.5   # CoV > 1.5 = bursty/irregular sightings
    LOW_BURSTINESS_COV = 0.3    # CoV < 0.3 = very regular/periodic
    
    # GPS spread thresholds (meters)
    HIGH_GPS_SPREAD = 200   # > 200m average spread = moving device
    LOW_GPS_SPREAD = 20     # < 20m spread = stationary device
    
    # Active presence ratio bucket size (seconds)
    PRESENCE_BUCKET_SECONDS = 60
    
    # Personal device keywords (checked in BT name/manufacturer, case-insensitive)
    PERSONAL_DEVICE_KEYWORDS = [
        'iphone', 'ipad', 'macbook', 'apple watch', 'airpods', 'airpod',
        'galaxy', 'samsung', 'pixel', 'oneplus', 'huawei', 'xiaomi', 'oppo', 'vivo',
        'redmi', 'realme', 'nokia', 'sony xperia', 'motorola moto',
        'fitbit', 'mi band', 'amazfit', 'band',
        'bose', 'jabra', 'beats', 'jbl', 'sony wh', 'sony wf',
        'tile', 'airtag', 'smarttag',
    ]
    
    # SAR/infrastructure equipment keywords (checked in BT name/manufacturer, case-insensitive)
    SAR_EQUIPMENT_KEYWORDS = [
        'garmin', 'kenwood', 'motorola solutions', 'baofeng', 'yaesu', 'icom',
        'hytera', 'sepura', 'harris', 'tait', 'vertex standard',
        'dji', 'drone', 'mavic', 'phantom', 'matrice',
        'gopro', 'flir', 'thermal',
        'ubiquiti', 'mikrotik', 'cisco', 'netgear', 'tp-link',
        'raspberry', 'esp32', 'arduino',
        'radio', 'transceiver', 'repeater',
    ]
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self.session_stats: Optional[SessionStats] = None
        self.analyses: List[DeviceAnalysis] = []
        self.whitelist: Set[str] = set()
        self.hq_coords: Optional[Tuple[float, float]] = None
        
        # Load whitelist
        self._load_whitelist()
        
        # Set HQ coordinates
        self._init_hq_location()
    
    def _load_whitelist(self):
        """Load device whitelist from file."""
        whitelist_path = DEVICE_WHITELIST_FILE
        if not os.path.isabs(whitelist_path):
            # Look in same directory as script, then current directory
            script_dir = os.path.dirname(os.path.abspath(__file__))
            possible_paths = [
                os.path.join(script_dir, whitelist_path),
                os.path.join(SD_STORAGE, whitelist_path),
                whitelist_path
            ]
        else:
            possible_paths = [whitelist_path]
        
        for path in possible_paths:
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                # Normalize MAC addresses (uppercase, colons)
                                mac = line.upper().replace('-', ':')
                                self.whitelist.add(mac)
                except Exception as e:
                    print(f"Warning: Could not read whitelist {path}: {e}")
                break
    
    def _init_hq_location(self):
        """Initialize HQ coordinates from settings or auto-detect."""
        if HQ_LATITUDE is not None and HQ_LONGITUDE is not None:
            self.hq_coords = (HQ_LATITUDE, HQ_LONGITUDE)
        else:
            # Auto-detect: use first sighting location as HQ
            self.hq_coords = self._auto_detect_hq()
    
    def _auto_detect_hq(self) -> Optional[Tuple[float, float]]:
        """Auto-detect HQ location from first sighting with GPS."""
        con = self.connect()
        try:
            # Try BT sightings first
            result = con.execute("""
                SELECT lat, lon FROM sightings 
                WHERE lat IS NOT NULL AND lon IS NOT NULL AND lat != 0 AND lon != 0
                ORDER BY ts_unix ASC LIMIT 1
            """).fetchone()
            
            if result:
                return (result[0], result[1])
            
            # Try WiFi associations
            result = con.execute("""
                SELECT lat, lon FROM wifi_associations 
                WHERE lat IS NOT NULL AND lon IS NOT NULL AND lat != 0 AND lon != 0
                ORDER BY ts_unix ASC LIMIT 1
            """).fetchone()
            
            if result:
                return (result[0], result[1])
            
            return None
        finally:
            con.close()
    
    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two GPS coordinates in meters using Haversine formula."""
        R = 6371000  # Earth's radius in meters
        
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        
        a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    def _analyze_gps_clustering(self, sightings_with_gps: List[Tuple[float, float]]) -> Tuple[Optional[float], Optional[float]]:
        """
        Analyze GPS coordinates to determine HQ proximity.
        
        Args:
            sightings_with_gps: List of (lat, lon) tuples for device sightings
            
        Returns:
            Tuple of (hq_ratio, avg_distance) where hq_ratio is 0-1 fraction of sightings near HQ
        """
        if not self.hq_coords or not sightings_with_gps:
            return None, None
        
        hq_lat, hq_lon = self.hq_coords
        near_hq_count = 0
        total_distance = 0
        
        for lat, lon in sightings_with_gps:
            distance = self._haversine_distance(hq_lat, hq_lon, lat, lon)
            total_distance += distance
            if distance <= HQ_RADIUS_METERS:
                near_hq_count += 1
        
        hq_ratio = near_hq_count / len(sightings_with_gps) if sightings_with_gps else None
        avg_distance = total_distance / len(sightings_with_gps) if sightings_with_gps else None
        
        return hq_ratio, avg_distance
    
    def _detect_sessions(self, timestamps: List[int]) -> int:
        """
        Detect number of distinct sessions from timestamps.
        
        A new session starts when there's a gap > SESSION_GAP_SECONDS.
        
        Args:
            timestamps: Sorted list of Unix timestamps
            
        Returns:
            Number of distinct sessions
        """
        if not timestamps or len(timestamps) < 2:
            return 1
        
        session_count = 1
        for i in range(1, len(timestamps)):
            gap = timestamps[i] - timestamps[i-1]
            if gap > SESSION_GAP_SECONDS:
                session_count += 1
        
        return session_count
    
    def _compute_rssi_trend(self, timestamps: List[int], rssi_values: List[float]) -> Tuple[Optional[float], Optional[float], bool]:
        """
        Compute RSSI trend (slope), standard deviation, and peak detection.
        
        A rise-then-fall RSSI pattern indicates a device passing by the scanner,
        which is a strong indicator of a person moving through the area.
        
        Returns:
            Tuple of (slope, std_dev, has_peak)
            - slope: dBm change per second (positive = getting stronger)
            - std_dev: Standard deviation of RSSI readings
            - has_peak: True if rise-then-fall pattern detected (pass-by)
        """
        if len(rssi_values) < 3:
            return None, None, False
        
        n = len(rssi_values)
        
        # Standard deviation
        mean_rssi = sum(rssi_values) / n
        variance = sum((r - mean_rssi) ** 2 for r in rssi_values) / n
        std_dev = math.sqrt(variance)
        
        # Linear regression for slope
        t0 = timestamps[0]
        t_norm = [float(t - t0) for t in timestamps]
        sum_t = sum(t_norm)
        sum_r = sum(rssi_values)
        sum_tr = sum(t * r for t, r in zip(t_norm, rssi_values))
        sum_t2 = sum(t * t for t in t_norm)
        
        denom = n * sum_t2 - sum_t * sum_t
        slope = (n * sum_tr - sum_t * sum_r) / denom if denom != 0 else 0
        
        # Peak detection: compare middle portion RSSI to edges
        if n >= 5:
            quarter = max(1, n // 4)
            edge_start = rssi_values[:quarter]
            edge_end = rssi_values[-quarter:]
            middle = rssi_values[quarter:-quarter] if quarter < n - quarter else rssi_values
            
            edge_start_mean = sum(edge_start) / len(edge_start)
            edge_end_mean = sum(edge_end) / len(edge_end)
            middle_mean = sum(middle) / len(middle) if middle else mean_rssi
            
            has_peak = (
                middle_mean > edge_start_mean + self.RSSI_PEAK_MIN_DELTA and
                middle_mean > edge_end_mean + self.RSSI_PEAK_MIN_DELTA
            )
        else:
            has_peak = False
        
        return slope, std_dev, has_peak
    
    def _compute_burstiness(self, timestamps: List[int]) -> Optional[float]:
        """
        Compute coefficient of variation (CoV) of inter-sighting intervals.
        
        High CoV = bursty/irregular (person passing through)
        Low CoV = regular/periodic (static SAR equipment scanning constantly)
        
        Returns:
            CoV value, or None if insufficient data
        """
        if len(timestamps) < 3:
            return None
        
        intervals = [timestamps[i] - timestamps[i-1] for i in range(1, len(timestamps))]
        intervals = [i for i in intervals if i > 0]  # Filter zero intervals
        
        if not intervals:
            return None
        
        mean_interval = sum(intervals) / len(intervals)
        if mean_interval == 0:
            return 0.0
        
        variance = sum((i - mean_interval) ** 2 for i in intervals) / len(intervals)
        std_dev = math.sqrt(variance)
        
        return std_dev / mean_interval
    
    def _compute_gps_spread(self, gps_coords: List[Tuple[float, float]]) -> Optional[float]:
        """
        Compute spatial spread (mean distance from centroid) of GPS coordinates.
        
        Large spread = device is moving (interesting for SAR)
        Small spread = stationary (likely infrastructure)
        
        Returns:
            Mean distance from centroid in meters, or None
        """
        if len(gps_coords) < 2:
            return None
        
        # Compute centroid
        avg_lat = sum(c[0] for c in gps_coords) / len(gps_coords)
        avg_lon = sum(c[1] for c in gps_coords) / len(gps_coords)
        
        # Compute mean distance from centroid
        distances = [self._haversine_distance(avg_lat, avg_lon, c[0], c[1]) for c in gps_coords]
        
        return sum(distances) / len(distances)
    
    def _compute_active_presence_ratio(self, timestamps: List[int], session_start: int, session_end: int) -> float:
        """
        Compute time-bucketed presence ratio.
        
        Divides session into fixed-size buckets and counts how many contain
        at least one sighting. More accurate than span-based presence ratio
        because a device seen once at minute 5 and once at minute 55 gets
        a low active ratio (2/60) vs high span ratio (50/60).
        
        Returns:
            Ratio of occupied buckets (0.0 to 1.0)
        """
        if not timestamps:
            return 0.0
        
        bucket_size = self.PRESENCE_BUCKET_SECONDS
        total_buckets = max(1, (session_end - session_start) // bucket_size + 1)
        
        occupied = set()
        for ts in timestamps:
            bucket_idx = (ts - session_start) // bucket_size
            occupied.add(bucket_idx)
        
        return min(1.0, len(occupied) / total_buckets)
    
    def _classify_device_name(self, name: Optional[str], manufacturer: Optional[str]) -> Optional[str]:
        """
        Classify device as personal or SAR equipment based on name/manufacturer.
        
        Returns:
            'personal', 'sar_equipment', or None (unknown)
        """
        search_text = ' '.join(filter(None, [name, manufacturer])).lower()
        if not search_text:
            return None
        
        for keyword in self.PERSONAL_DEVICE_KEYWORDS:
            if keyword in search_text:
                return 'personal'
        
        for keyword in self.SAR_EQUIPMENT_KEYWORDS:
            if keyword in search_text:
                return 'sar_equipment'
        
        return None
    
    def _classify_sar_role(
        self,
        analysis: DeviceAnalysis,
        early_late_gps_distance: Optional[float] = None,
    ) -> Optional[str]:
        """Classify a device as SAR HQ equipment, SAR TEAM member device, or None.

        SAR HQ:   strong signal at both session start AND end, with location
                  evidence that the device stays at a fixed point (HQ).
        SAR TEAM: seen continuously throughout the session with consistent
                  signal strength (device carried alongside the scanner).

        Returns:
            "SAR HQ", "SAR TEAM", or None
        """
        # --- SAR HQ detection ---
        # Strong RSSI at both session boundaries
        strong_at_boundaries = (
            analysis.early_presence
            and analysis.late_presence
            and analysis.early_rssi is not None
            and analysis.early_rssi > -70
            and analysis.late_rssi is not None
            and analysis.late_rssi > -70
        )

        if strong_at_boundaries:
            # Need location evidence: HQ ratio high, or early/late GPS close,
            # or no GPS data (can't contradict).
            location_ok = False
            if analysis.hq_ratio is not None and analysis.hq_ratio > 0.70:
                location_ok = True
            if early_late_gps_distance is not None and early_late_gps_distance < 150:
                location_ok = True
            if analysis.hq_ratio is None and early_late_gps_distance is None:
                # No GPS data at all – boundary RSSI alone is strong enough.
                location_ok = True
            if location_ok:
                return "SAR HQ"

        # --- SAR TEAM detection ---
        # Seen in most time buckets with consistent signal
        if (
            analysis.active_presence_ratio is not None
            and analysis.active_presence_ratio >= 0.50
            and analysis.presence_ratio >= 0.60
        ):
            rssi_consistent = (
                analysis.rssi_std_dev is not None
                and analysis.rssi_std_dev < 10.0
            )
            very_high_presence = analysis.active_presence_ratio >= 0.70
            if rssi_consistent or very_high_presence:
                return "SAR TEAM"

        return None

    def is_whitelisted(self, mac: str) -> bool:
        """Check if a MAC address is in the whitelist."""
        # Normalize MAC for comparison
        normalized = mac.upper().replace('-', ':')
        return normalized in self.whitelist
        
    def connect(self) -> sqlite3.Connection:
        """Create database connection."""
        return sqlite3.connect(self.db_path)
    
    def get_session_stats(self) -> Optional[SessionStats]:
        """Calculate overall session statistics from all sightings."""
        con = self.connect()
        try:
            # Get BT session boundaries
            bt_stats = con.execute("""
                SELECT MIN(ts_unix), MAX(ts_unix), COUNT(*), COUNT(DISTINCT addr)
                FROM sightings WHERE ts_unix IS NOT NULL
            """).fetchone()
            
            # Get WiFi session boundaries
            wifi_stats = con.execute("""
                SELECT MIN(ts_unix), MAX(ts_unix), COUNT(*), COUNT(DISTINCT mac)
                FROM wifi_associations WHERE ts_unix IS NOT NULL
            """).fetchone()
            
            # Combine to get overall session window
            bt_min, bt_max, bt_count, bt_devices = bt_stats
            wifi_min, wifi_max, wifi_count, wifi_devices = wifi_stats
            
            # Handle empty tables
            times = [t for t in [bt_min, bt_max, wifi_min, wifi_max] if t is not None]
            if not times:
                return None
            
            start_time = min(times)
            end_time = max(times)
            duration = end_time - start_time
            
            if duration <= 0:
                duration = 1  # Avoid division by zero
            
            return SessionStats(
                start_time=start_time,
                end_time=end_time,
                duration=duration,
                total_bt_sightings=bt_count or 0,
                total_wifi_associations=wifi_count or 0,
                total_bt_devices=bt_devices or 0,
                total_wifi_devices=wifi_devices or 0
            )
        finally:
            con.close()
    
    def analyze_bt_device(self, addr: str, session: SessionStats) -> DeviceAnalysis:
        """Analyze a single Bluetooth device."""
        # Check whitelist first
        is_whitelisted = self.is_whitelisted(addr)
        
        con = self.connect()
        try:
            # Get device info
            device = con.execute(
                "SELECT first_seen, last_seen, confidence, name, manufacturer FROM devices WHERE addr = ?",
                (addr,)
            ).fetchone()
            
            if not device:
                return None
            
            first_seen, last_seen, old_confidence, bt_name, bt_manufacturer = device
            
            # Get all sightings for this device with GPS, scanner, and service data
            sightings = con.execute("""
                SELECT ts_unix, rssi, lat, lon, scanner_name, service_uuid, local_name FROM sightings 
                WHERE addr = ? AND ts_unix IS NOT NULL
                ORDER BY ts_unix
            """, (addr,)).fetchall()
            
            sighting_count = len(sightings)
            
            # Calculate average RSSI
            rssi_values = [s[1] for s in sightings if s[1] is not None]
            avg_rssi = sum(rssi_values) / len(rssi_values) if rssi_values else None
            
            # Extract GPS coordinates
            gps_coords = [(s[2], s[3]) for s in sightings 
                         if s[2] is not None and s[3] is not None and s[2] != 0 and s[3] != 0]
            
            # Analyze GPS clustering
            hq_ratio, avg_distance = self._analyze_gps_clustering(gps_coords)
            
            # Detect sessions from timestamps
            timestamps = [s[0] for s in sightings]
            session_count = self._detect_sessions(timestamps)
            
            # Calculate presence ratio (capped at 1.0)
            device_duration = last_seen - first_seen
            presence_ratio = min(1.0, device_duration / session.duration) if session.duration > 0 else 0
            
            # Analyze session boundaries
            boundary_window = session.duration * self.BOUNDARY_PERCENT
            early_cutoff = session.start_time + boundary_window
            late_cutoff = session.end_time - boundary_window
            
            early_sightings = [(s[0], s[1]) for s in sightings if s[0] <= early_cutoff]
            late_sightings = [(s[0], s[1]) for s in sightings if s[0] >= late_cutoff]
            
            early_presence = len(early_sightings) > 0
            late_presence = len(late_sightings) > 0
            
            early_rssi_vals = [r for _, r in early_sightings if r is not None]
            late_rssi_vals = [r for _, r in late_sightings if r is not None]
            
            early_rssi = sum(early_rssi_vals) / len(early_rssi_vals) if early_rssi_vals else None
            late_rssi = sum(late_rssi_vals) / len(late_rssi_vals) if late_rssi_vals else None
            
            # --- Enhanced analysis computations (v2) ---
            # RSSI trend and variance
            rssi_timestamps = [s[0] for s in sightings if s[1] is not None]
            rssi_vals_ordered = [s[1] for s in sightings if s[1] is not None]
            _, rssi_std_dev, rssi_has_peak = self._compute_rssi_trend(rssi_timestamps, rssi_vals_ordered)
            
            # MAC randomization check
            is_randomized = is_locally_administered_mac(addr)
            
            # Sighting burstiness
            burstiness_cov = self._compute_burstiness(timestamps)
            
            # GPS spatial spread
            gps_spread = self._compute_gps_spread(gps_coords)
            
            # Active (time-bucketed) presence ratio
            active_presence = self._compute_active_presence_ratio(
                timestamps, session.start_time, session.end_time
            )
            
            # Scanner count
            scanner_names = set(s[4] for s in sightings if s[4] is not None)
            scanner_count_val = max(1, len(scanner_names))
            
            # OUI-based vendor and device type enrichment (hybrid approach for BT too)
            vendor_name, guessed_type = lookup_and_guess(addr)
            
            # Collect unique service UUIDs from all sightings for classification
            service_uuids = list(set(s[5] for s in sightings if s[5]))
            
            # Expanded device type classification (name + manufacturer + UUIDs + OUI)
            classified_type = classify_device(
                name=bt_name,
                manufacturer=bt_manufacturer,
                service_uuids=service_uuids,
                oui_vendor=vendor_name,
                is_randomized_mac=is_randomized,
            )
            if classified_type:
                guessed_type = classified_type
            
            # Calculate new confidence
            if is_whitelisted:
                # Whitelisted devices automatically get confidence 0
                new_confidence = 0
                factors = ["Whitelisted device (SAR team equipment) → 0"]
            else:
                new_confidence, factors = self._calculate_confidence(
                    presence_ratio=presence_ratio,
                    sighting_count=sighting_count,
                    session_duration=session.duration,
                    early_presence=early_presence,
                    late_presence=late_presence,
                    early_rssi=early_rssi,
                    late_rssi=late_rssi,
                    avg_rssi=avg_rssi,
                    hq_ratio=hq_ratio,
                    avg_distance_from_hq=avg_distance,
                    session_count=session_count,
                    rssi_std_dev=rssi_std_dev,
                    rssi_has_peak=rssi_has_peak,
                    is_randomized_mac=is_randomized,
                    device_name=bt_name,
                    manufacturer_name=bt_manufacturer,
                    burstiness_cov=burstiness_cov,
                    gps_spread=gps_spread,
                    scanner_count=scanner_count_val,
                    active_presence_ratio=active_presence,
                )
            
            return DeviceAnalysis(
                mac=addr,
                device_type="bt",
                first_seen=first_seen,
                last_seen=last_seen,
                sighting_count=sighting_count,
                avg_rssi=avg_rssi,
                presence_ratio=presence_ratio,
                early_presence=early_presence,
                late_presence=late_presence,
                early_rssi=early_rssi,
                late_rssi=late_rssi,
                old_confidence=old_confidence,
                new_confidence=new_confidence,
                factors=factors,
                hq_ratio=hq_ratio,
                avg_distance_from_hq=avg_distance,
                session_count=session_count,
                whitelisted=is_whitelisted,
                vendor_name=vendor_name,
                guessed_type=guessed_type,
                rssi_std_dev=rssi_std_dev,
                rssi_has_peak=rssi_has_peak,
                is_randomized_mac=is_randomized,
                device_name=bt_name,
                manufacturer_name=bt_manufacturer,
                burstiness_cov=burstiness_cov,
                active_presence_ratio=active_presence,
                gps_spread_meters=gps_spread,
                scanner_count=scanner_count_val,
            )
        finally:
            con.close()
    
    def analyze_wifi_device(self, mac: str, session: SessionStats) -> DeviceAnalysis:
        """Analyze a single WiFi device."""
        # Check whitelist first
        is_whitelisted = self.is_whitelisted(mac)
        
        con = self.connect()
        try:
            # Get device info
            device = con.execute(
                "SELECT first_seen, last_seen, confidence FROM wifi_devices WHERE mac = ?",
                (mac,)
            ).fetchone()
            
            if not device:
                return None
            
            first_seen, last_seen, old_confidence = device
            
            # Get all associations for this device with GPS and scanner data
            associations = con.execute("""
                SELECT ts_unix, rssi, lat, lon, scanner_name FROM wifi_associations 
                WHERE mac = ? AND ts_unix IS NOT NULL
                ORDER BY ts_unix
            """, (mac,)).fetchall()
            
            sighting_count = len(associations)
            
            # Calculate average RSSI
            rssi_values = [a[1] for a in associations if a[1] is not None]
            avg_rssi = sum(rssi_values) / len(rssi_values) if rssi_values else None
            
            # Extract GPS coordinates
            gps_coords = [(a[2], a[3]) for a in associations 
                         if a[2] is not None and a[3] is not None and a[2] != 0 and a[3] != 0]
            
            # Analyze GPS clustering
            hq_ratio, avg_distance = self._analyze_gps_clustering(gps_coords)
            
            # Detect sessions from timestamps
            timestamps = [a[0] for a in associations]
            session_count = self._detect_sessions(timestamps)
            
            # Calculate presence ratio (capped at 1.0)
            device_duration = last_seen - first_seen
            presence_ratio = min(1.0, device_duration / session.duration) if session.duration > 0 else 0
            
            # Analyze session boundaries
            boundary_window = session.duration * self.BOUNDARY_PERCENT
            early_cutoff = session.start_time + boundary_window
            late_cutoff = session.end_time - boundary_window
            
            early_associations = [(ts, rssi) for ts, rssi, _, _, _ in associations if ts <= early_cutoff]
            late_associations = [(ts, rssi) for ts, rssi, _, _, _ in associations if ts >= late_cutoff]
            
            early_presence = len(early_associations) > 0
            late_presence = len(late_associations) > 0
            
            early_rssi_vals = [r for _, r in early_associations if r is not None]
            late_rssi_vals = [r for _, r in late_associations if r is not None]
            
            early_rssi = sum(early_rssi_vals) / len(early_rssi_vals) if early_rssi_vals else None
            late_rssi = sum(late_rssi_vals) / len(late_rssi_vals) if late_rssi_vals else None
            
            # --- Enhanced analysis computations (v2) ---
            # RSSI trend and variance
            rssi_timestamps = [a[0] for a in associations if a[1] is not None]
            rssi_vals_ordered = [a[1] for a in associations if a[1] is not None]
            _, rssi_std_dev, rssi_has_peak = self._compute_rssi_trend(rssi_timestamps, rssi_vals_ordered)
            
            # MAC randomization check
            is_randomized = is_locally_administered_mac(mac)
            
            # Sighting burstiness
            burstiness_cov = self._compute_burstiness(timestamps)
            
            # GPS spatial spread
            gps_spread = self._compute_gps_spread(gps_coords)
            
            # Active (time-bucketed) presence ratio
            active_presence = self._compute_active_presence_ratio(
                timestamps, session.start_time, session.end_time
            )
            
            # Scanner count
            scanner_names = set(a[4] for a in associations if a[4] is not None)
            scanner_count_val = max(1, len(scanner_names))
            
            # WiFi-specific: SSID analysis
            ssid_data = con.execute("""
                SELECT DISTINCT ssid FROM wifi_associations 
                WHERE mac = ? AND ssid IS NOT NULL AND ssid != '' AND ssid != '<hidden>'
            """, (mac,)).fetchall()
            unique_ssids = [row[0] for row in ssid_data]
            ssid_count = len(unique_ssids)
            
            # WiFi-specific: Packet type analysis (Beacon = AP, ProbeRequest = client)
            packet_type_data = con.execute("""
                SELECT packet_type, COUNT(*) FROM wifi_associations 
                WHERE mac = ? AND packet_type IS NOT NULL
                GROUP BY packet_type
            """, (mac,)).fetchall()
            pt_counts = {pt: cnt for pt, cnt in packet_type_data}
            beacon_count = pt_counts.get('Beacon', 0)
            probe_count = pt_counts.get('ProbeRequest', 0)
            
            if beacon_count > 0 and probe_count == 0:
                is_beacon_device = True
            elif probe_count > 0 and beacon_count == 0:
                is_beacon_device = False
            else:
                is_beacon_device = None  # Mixed or unknown
            
            # OUI-based vendor and device type enrichment
            vendor_name, guessed_type = lookup_and_guess(mac)
            
            # Expanded device type classification (OUI + SSIDs + beacon + MAC)
            classified_type = classify_device(
                oui_vendor=vendor_name,
                ssids=unique_ssids,
                is_beacon=is_beacon_device,
                is_randomized_mac=is_randomized,
            )
            if classified_type:
                guessed_type = classified_type
            
            # Compute early/late GPS centroid distance for SAR HQ detection
            early_gps = [(a[2], a[3]) for a in associations
                         if a[0] <= early_cutoff
                         and a[2] is not None and a[3] is not None
                         and a[2] != 0 and a[3] != 0]
            late_gps = [(a[2], a[3]) for a in associations
                        if a[0] >= late_cutoff
                        and a[2] is not None and a[3] is not None
                        and a[2] != 0 and a[3] != 0]

            early_late_gps_distance: Optional[float] = None
            if early_gps and late_gps:
                e_lat = sum(c[0] for c in early_gps) / len(early_gps)
                e_lon = sum(c[1] for c in early_gps) / len(early_gps)
                l_lat = sum(c[0] for c in late_gps) / len(late_gps)
                l_lon = sum(c[1] for c in late_gps) / len(late_gps)
                early_late_gps_distance = self._haversine_distance(e_lat, e_lon, l_lat, l_lon)

            # Calculate new confidence
            if is_whitelisted:
                # Whitelisted devices automatically get confidence 0
                new_confidence = 0
                factors = ["Whitelisted device (SAR team equipment) → 0"]
            else:
                new_confidence, factors = self._calculate_confidence(
                    presence_ratio=presence_ratio,
                    sighting_count=sighting_count,
                    session_duration=session.duration,
                    early_presence=early_presence,
                    late_presence=late_presence,
                    early_rssi=early_rssi,
                    late_rssi=late_rssi,
                    avg_rssi=avg_rssi,
                    hq_ratio=hq_ratio,
                    avg_distance_from_hq=avg_distance,
                    session_count=session_count,
                    rssi_std_dev=rssi_std_dev,
                    rssi_has_peak=rssi_has_peak,
                    ssid_count=ssid_count,
                    is_randomized_mac=is_randomized,
                    manufacturer_name=vendor_name,
                    burstiness_cov=burstiness_cov,
                    is_beacon_device=is_beacon_device,
                    gps_spread=gps_spread,
                    scanner_count=scanner_count_val,
                    active_presence_ratio=active_presence,
                )
            
            wifi_analysis = DeviceAnalysis(
                mac=mac,
                device_type="wifi",
                first_seen=first_seen,
                last_seen=last_seen,
                sighting_count=sighting_count,
                avg_rssi=avg_rssi,
                presence_ratio=presence_ratio,
                early_presence=early_presence,
                late_presence=late_presence,
                early_rssi=early_rssi,
                late_rssi=late_rssi,
                old_confidence=old_confidence,
                new_confidence=new_confidence,
                factors=factors,
                hq_ratio=hq_ratio,
                avg_distance_from_hq=avg_distance,
                session_count=session_count,
                whitelisted=is_whitelisted,
                vendor_name=vendor_name,
                guessed_type=guessed_type,
                rssi_std_dev=rssi_std_dev,
                rssi_has_peak=rssi_has_peak,
                ssid_count=ssid_count,
                ssid_list=unique_ssids,
                is_beacon_device=is_beacon_device,
                is_randomized_mac=is_randomized,
                burstiness_cov=burstiness_cov,
                active_presence_ratio=active_presence,
                gps_spread_meters=gps_spread,
                scanner_count=scanner_count_val,
            )

            # Classify SAR role (HQ equipment vs team-carried device)
            wifi_analysis.sar_role = self._classify_sar_role(
                wifi_analysis, early_late_gps_distance
            )

            return wifi_analysis
        finally:
            con.close()
    
    def _calculate_confidence(
        self,
        presence_ratio: float,
        sighting_count: int,
        session_duration: int,
        early_presence: bool,
        late_presence: bool,
        early_rssi: Optional[float],
        late_rssi: Optional[float],
        avg_rssi: Optional[float],
        hq_ratio: Optional[float] = None,
        avg_distance_from_hq: Optional[float] = None,
        session_count: int = 1,
        # Enhanced analysis parameters (v2)
        rssi_std_dev: Optional[float] = None,
        rssi_has_peak: bool = False,
        ssid_count: Optional[int] = None,
        is_randomized_mac: bool = False,
        device_name: Optional[str] = None,
        manufacturer_name: Optional[str] = None,
        burstiness_cov: Optional[float] = None,
        is_beacon_device: Optional[bool] = None,
        gps_spread: Optional[float] = None,
        scanner_count: int = 1,
        active_presence_ratio: Optional[float] = None,
    ) -> Tuple[int, List[str]]:
        """
        Calculate confidence score based on various factors.
        
        Returns:
            Tuple of (confidence_score, list_of_factor_explanations)
        """
        # Start with neutral baseline
        confidence = 50
        factors = []
        
        # Factor 1: Presence ratio
        # High presence = likely SAR team (device present throughout)
        if presence_ratio > self.HIGH_PRESENCE_RATIO:
            confidence -= 30
            factors.append(f"High presence ratio ({presence_ratio:.1%}) → -30 (likely SAR team)")
        elif presence_ratio > self.MEDIUM_PRESENCE_RATIO:
            confidence -= 15
            factors.append(f"Medium presence ratio ({presence_ratio:.1%}) → -15")
        elif presence_ratio < 0.20:
            confidence += 15
            factors.append(f"Low presence ratio ({presence_ratio:.1%}) → +15 (brief appearance)")
        
        # Factor 2: Session boundary presence with strong signal
        # Strong signal at BOTH start AND end = likely HQ equipment
        if early_presence and late_presence:
            if (early_rssi is not None and early_rssi > self.STRONG_RSSI_THRESHOLD and
                late_rssi is not None and late_rssi > self.STRONG_RSSI_THRESHOLD):
                confidence -= 25
                factors.append(f"Strong RSSI at start ({early_rssi:.0f}) AND end ({late_rssi:.0f}) → -25 (HQ equipment)")
            elif early_rssi is not None and late_rssi is not None:
                confidence -= 10
                factors.append(f"Present at session boundaries → -10")
        
        # Factor 3: Mid-session only appearance (positive indicator)
        # Device appears only in the middle = more likely missing person
        if not early_presence and not late_presence and sighting_count > 0:
            confidence += 25
            factors.append("Only mid-session appearance → +25 (possible target)")
        elif not early_presence and late_presence:
            confidence += 10
            factors.append("Not present at start, appeared later → +10")
        elif early_presence and not late_presence:
            confidence += 10
            factors.append("Present at start, disappeared → +10")
        
        # Factor 4: Sighting frequency relative to session duration
        # Very frequent sightings = always present = SAR team
        if session_duration > 60:  # Only if session > 1 minute
            # Assume ~30 seconds per scan cycle for BT
            expected_max_sightings = session_duration / 30
            sighting_rate = sighting_count / expected_max_sightings if expected_max_sightings > 0 else 0
            
            if sighting_rate > self.HIGH_SIGHTING_RATE:
                confidence -= 15
                factors.append(f"Very high sighting rate ({sighting_rate:.1%}) → -15 (constantly present)")
            elif sighting_count <= 3:
                confidence += 10
                factors.append(f"Low sighting count ({sighting_count}) → +10 (fleeting)")
        
        # Factor 5: Very weak signal throughout
        # Consistently weak signal might indicate distant/mobile target
        if avg_rssi is not None and avg_rssi < -80:
            confidence += 5
            factors.append(f"Weak average signal ({avg_rssi:.0f} dBm) → +5 (distant)")
        elif avg_rssi is not None and avg_rssi > -50:
            confidence -= 5
            factors.append(f"Very strong average signal ({avg_rssi:.0f} dBm) → -5 (close/HQ)")
        
        # Factor 6: GPS clustering - HQ proximity analysis
        # Devices seen mostly near HQ are likely SAR team
        if hq_ratio is not None:
            if hq_ratio > self.HQ_RATIO_HIGH:
                confidence -= 20
                factors.append(f"Seen mostly near HQ ({hq_ratio:.0%} within {HQ_RADIUS_METERS}m) → -20 (base equipment)")
            elif hq_ratio < self.HQ_RATIO_LOW:
                confidence += 15
                factors.append(f"Rarely seen near HQ ({hq_ratio:.0%}) → +15 (field device)")
        
        # Factor 7: Average distance from HQ
        # Devices consistently far from HQ are more interesting
        if avg_distance_from_hq is not None:
            if avg_distance_from_hq > 500:  # > 500m average
                confidence += 10
                factors.append(f"Avg distance from HQ: {avg_distance_from_hq:.0f}m → +10 (far from base)")
            elif avg_distance_from_hq < 50:  # < 50m average
                confidence -= 10
                factors.append(f"Avg distance from HQ: {avg_distance_from_hq:.0f}m → -10 (at base)")
        
        # Factor 8: Multi-session detection
        # Devices seen across multiple sessions are more likely SAR team (persistent)
        if session_count > 1:
            if session_count >= 3:
                confidence -= 15
                factors.append(f"Seen in {session_count} separate sessions → -15 (persistent presence)")
            else:
                confidence -= 5
                factors.append(f"Seen in {session_count} sessions → -5")
        
        # ---- Enhanced factors (v2) ----
        
        # Factor 9: RSSI Trend / Variance (movement detection)
        # A rise-then-fall RSSI pattern indicates someone passing by the scanner
        if rssi_has_peak:
            confidence += 15
            factors.append("RSSI rise-then-fall pattern detected → +15 (device passed by)")
        elif rssi_std_dev is not None:
            if rssi_std_dev > self.RSSI_HIGH_VARIANCE_THRESHOLD:
                confidence += 8
                factors.append(f"High RSSI variance (σ={rssi_std_dev:.1f} dBm) → +8 (moving device)")
            elif rssi_std_dev < self.RSSI_LOW_VARIANCE_THRESHOLD and sighting_count >= 5:
                confidence -= 8
                factors.append(f"Low RSSI variance (σ={rssi_std_dev:.1f} dBm) → -8 (stationary)")
        
        # Factor 10: WiFi SSID Probing (WiFi only)
        # Personal phones probe for multiple remembered networks
        if ssid_count is not None:
            if ssid_count >= 3:
                confidence += 12
                factors.append(f"Probes {ssid_count} unique SSIDs → +12 (personal device)")
            elif ssid_count >= 1:
                confidence += 5
                factors.append(f"Probes {ssid_count} unique SSID(s) → +5")
        
        # Factor 11: MAC Randomization
        # Randomized MACs indicate modern smartphones/tablets (iOS, Android)
        if is_randomized_mac:
            confidence += 10
            factors.append("Randomized MAC (locally-administered) → +10 (modern personal device)")
        
        # Factor 12: Device Name/Manufacturer Classification
        # Known personal device names boost confidence; SAR equipment lowers it
        device_classification = self._classify_device_name(device_name, manufacturer_name)
        device_name_str = ' / '.join(filter(None, [device_name, manufacturer_name])) or 'unknown'
        if device_classification == 'personal':
            confidence += 12
            factors.append(f"Personal device identified ({device_name_str}) → +12")
        elif device_classification == 'sar_equipment':
            confidence -= 15
            factors.append(f"SAR/infrastructure equipment ({device_name_str}) → -15")
        
        # Factor 13: Sighting Burstiness (temporal clustering)
        # Bursty/irregular sightings suggest a person passing through
        if burstiness_cov is not None:
            if burstiness_cov > self.HIGH_BURSTINESS_COV:
                confidence += 8
                factors.append(f"Bursty sighting pattern (CoV={burstiness_cov:.2f}) → +8 (irregular)")
            elif burstiness_cov < self.LOW_BURSTINESS_COV:
                confidence -= 8
                factors.append(f"Regular sighting pattern (CoV={burstiness_cov:.2f}) → -8 (periodic)")
        
        # Factor 14: WiFi Packet Type (WiFi only)
        # Beacon-only = access point (infrastructure), ProbeRequest-only = client device
        if is_beacon_device is True:
            confidence -= 20
            factors.append("Beacon-only device (Access Point) → -20 (infrastructure)")
        elif is_beacon_device is False:
            confidence += 5
            factors.append("ProbeRequest-only device (client) → +5 (personal device)")
        
        # Factor 15: GPS Spatial Spread
        # Large spread = device is moving through the area
        if gps_spread is not None:
            if gps_spread > self.HIGH_GPS_SPREAD:
                confidence += 10
                factors.append(f"Large GPS spread ({gps_spread:.0f}m) → +10 (moving device)")
            elif gps_spread < self.LOW_GPS_SPREAD and sighting_count >= 5:
                confidence -= 5
                factors.append(f"Tiny GPS spread ({gps_spread:.1f}m) → -5 (stationary)")
        
        # Factor 16: Cross-Scanner Consistency
        # Devices seen by many scanners at once are likely ubiquitous SAR equipment
        if scanner_count >= 3:
            confidence -= 8
            factors.append(f"Seen by {scanner_count} scanners → -8 (ubiquitous)")
        elif scanner_count == 1 and sighting_count <= 5:
            confidence += 3
            factors.append("Single scanner, few sightings → +3 (localized)")
        
        # Factor 17: Active Presence Ratio (more accurate than span-based)
        # Detects discrepancy between time span and actual sighting density
        if active_presence_ratio is not None:
            if presence_ratio > 0.5 and active_presence_ratio < 0.15:
                confidence += 10
                factors.append(f"Active presence much lower than span ({active_presence_ratio:.1%} vs {presence_ratio:.1%}) → +10 (sporadic)")
        
        # Factor 18: Signal Convergence (meta-factor)
        # When multiple independent signals agree, boost the overall score
        positive_count = sum(1 for f in factors if '→ +' in f)
        negative_count = sum(1 for f in factors if '→ -' in f)
        
        if positive_count >= 5:
            confidence += 10
            factors.append(f"Strong signal convergence: {positive_count} positive indicators → +10")
        elif positive_count >= 4:
            confidence += 5
            factors.append(f"Signal convergence: {positive_count} positive indicators → +5")
        
        if negative_count >= 5:
            confidence -= 10
            factors.append(f"Strong signal convergence: {negative_count} negative indicators → -10")
        elif negative_count >= 4:
            confidence -= 5
            factors.append(f"Signal convergence: {negative_count} negative indicators → -5")
        
        # Clamp to valid range
        confidence = max(0, min(100, confidence))
        
        return confidence, factors
    
    def analyze_all(self) -> Tuple[SessionStats, List[DeviceAnalysis]]:
        """Analyze all devices in the database."""
        # Get session statistics
        self.session_stats = self.get_session_stats()
        if not self.session_stats:
            print("No sighting data found in database.")
            return None, []
        
        self.analyses = []
        con = self.connect()
        
        try:
            # Get all BT devices
            bt_devices = con.execute("SELECT addr FROM devices").fetchall()
            for (addr,) in bt_devices:
                analysis = self.analyze_bt_device(addr, self.session_stats)
                if analysis:
                    self.analyses.append(analysis)
            
            # Get all WiFi devices
            wifi_devices = con.execute("SELECT mac FROM wifi_devices").fetchall()
            for (mac,) in wifi_devices:
                analysis = self.analyze_wifi_device(mac, self.session_stats)
                if analysis:
                    self.analyses.append(analysis)
        finally:
            con.close()
        
        return self.session_stats, self.analyses

    @staticmethod
    def _find_matching_bracket_end(text: str, start_index: int = 0) -> Optional[int]:
        """Return index of the matching closing bracket for text[start_index] == '['."""
        if start_index < 0 or start_index >= len(text) or text[start_index] != '[':
            return None

        depth = 0
        for idx in range(start_index, len(text)):
            ch = text[idx]
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    return idx
        return None

    def _strip_leading_type_tags(self, notes: str) -> str:
        """Remove one or more leading [type:...] tags from BT notes.

        Handles nested brackets inside the type value, e.g. [type:phone [heur]].
        """
        cleaned = (notes or '').strip()

        while cleaned.startswith('[type:'):
            tag_end = self._find_matching_bracket_end(cleaned, 0)
            if tag_end is None:
                # Malformed tag: best-effort drop the prefix to avoid carrying stale artifacts.
                cleaned = cleaned[len('[type:'):].lstrip()
                break
            cleaned = cleaned[tag_end + 1:].lstrip()

        return cleaned
    
    def apply_updates(self) -> Dict[str, int]:
        """Apply confidence updates and enrichment data to the database."""
        if not self.analyses:
            return {"bt_updated": 0, "wifi_updated": 0, "wifi_enriched": 0}
        
        con = self.connect()
        bt_count = 0
        wifi_count = 0
        wifi_enriched = 0
        
        try:
            for analysis in self.analyses:
                if analysis.device_type == "bt":
                    row = con.execute("SELECT notes FROM devices WHERE addr = ?", (analysis.mac,)).fetchone()
                    existing = (row[0] or '') if row else ''
                    base_notes = self._strip_leading_type_tags(existing)

                    if analysis.guessed_type:
                        # Replace previous classifier tag instead of appending repeatedly.
                        new_notes = f"[type:{analysis.guessed_type}] {base_notes}".strip()
                        con.execute(
                            "UPDATE devices SET confidence = ?, notes = ? WHERE addr = ?",
                            (analysis.new_confidence, new_notes, analysis.mac)
                        )
                    else:
                        con.execute(
                            "UPDATE devices SET confidence = ?, notes = ? WHERE addr = ?",
                            (analysis.new_confidence, base_notes, analysis.mac)
                        )
                    bt_count += 1
                else:
                    # Compose device_type: combine classifier type with SAR role
                    parts = []
                    if analysis.guessed_type:
                        parts.append(analysis.guessed_type)
                    if analysis.sar_role:
                        parts.append(analysis.sar_role)
                    device_type_value = " | ".join(parts)

                    # Update confidence, vendor, and device_type for WiFi devices
                    con.execute(
                        "UPDATE wifi_devices SET confidence = ?, vendor = ?, device_type = ? WHERE mac = ?",
                        (analysis.new_confidence, 
                         analysis.vendor_name or "", 
                         device_type_value, 
                         analysis.mac)
                    )
                    wifi_count += 1
                    if analysis.vendor_name or analysis.guessed_type:
                        wifi_enriched += 1
            
            con.commit()
        finally:
            con.close()
        
        return {"bt_updated": bt_count, "wifi_updated": wifi_count, "wifi_enriched": wifi_enriched}
    
    def get_summary(self) -> Dict:
        """Get analysis summary for reporting."""
        if not self.session_stats or not self.analyses:
            return {}
        
        bt_analyses = [a for a in self.analyses if a.device_type == "bt"]
        wifi_analyses = [a for a in self.analyses if a.device_type == "wifi"]
        
        high_confidence = [a for a in self.analyses if a.new_confidence >= 70]
        low_confidence = [a for a in self.analyses if a.new_confidence <= 30]
        whitelisted = [a for a in self.analyses if a.whitelisted]
        
        # Count devices with GPS data
        has_gps = [a for a in self.analyses if a.hq_ratio is not None]
        multi_session = [a for a in self.analyses if a.session_count > 1]
        randomized_macs = [a for a in self.analyses if a.is_randomized_mac]
        beacon_devices = [a for a in self.analyses if a.is_beacon_device is True]
        with_rssi_peak = [a for a in self.analyses if a.rssi_has_peak]
        
        return {
            "session": {
                "start": datetime.fromtimestamp(self.session_stats.start_time).isoformat(),
                "end": datetime.fromtimestamp(self.session_stats.end_time).isoformat(),
                "duration_seconds": self.session_stats.duration,
                "duration_human": f"{self.session_stats.duration // 60}m {self.session_stats.duration % 60}s"
            },
            "devices": {
                "bt_total": len(bt_analyses),
                "wifi_total": len(wifi_analyses),
                "high_confidence": len(high_confidence),
                "low_confidence": len(low_confidence),
                "whitelisted": len(whitelisted),
                "with_gps_data": len(has_gps),
                "multi_session": len(multi_session),
                "randomized_macs": len(randomized_macs),
                "beacon_devices": len(beacon_devices),
                "rssi_peak_detected": len(with_rssi_peak)
            },
            "config": {
                "hq_location": self.hq_coords,
                "hq_radius_meters": HQ_RADIUS_METERS,
                "session_gap_seconds": SESSION_GAP_SECONDS,
                "whitelist_count": len(self.whitelist)
            },
            "high_confidence_devices": [
                {"mac": a.mac, "type": a.device_type, "confidence": a.new_confidence}
                for a in sorted(high_confidence, key=lambda x: -x.new_confidence)[:10]
            ]
        }


def run_analysis(dry_run: bool = False, verbose: bool = False) -> Dict:
    """
    Run confidence analysis on all devices.
    
    Args:
        dry_run: If True, don't apply changes to database
        verbose: If True, print detailed analysis
    
    Returns:
        Summary dictionary with results
    """
    analyzer = ConfidenceAnalyzer()
    
    print(f"\n{'='*60}")
    print("SAR Device Confidence Analyzer")
    print(f"{'='*60}")
    print(f"Database: {analyzer.db_path}")
    print(f"Mode: {'DRY RUN (no changes)' if dry_run else 'LIVE (will update database)'}")
    print()
    
    # Run analysis
    session, analyses = analyzer.analyze_all()
    
    if not session:
        print("ERROR: No data to analyze.")
        return {"error": "No data to analyze"}
    
    # Print session info
    print(f"Session window:")
    print(f"  Start: {datetime.fromtimestamp(session.start_time)}")
    print(f"  End:   {datetime.fromtimestamp(session.end_time)}")
    print(f"  Duration: {session.duration // 60}m {session.duration % 60}s")
    print(f"  BT devices: {session.total_bt_devices}, sightings: {session.total_bt_sightings}")
    print(f"  WiFi devices: {session.total_wifi_devices}, associations: {session.total_wifi_associations}")
    print()
    
    # Print analysis results
    if verbose:
        print(f"{'='*60}")
        print("Device Analysis Details:")
        print(f"{'='*60}")
        for analysis in sorted(analyses, key=lambda x: -x.new_confidence):
            avg_rssi_str = f"{analysis.avg_rssi:.0f}" if analysis.avg_rssi else "N/A"
            print(f"\n[{analysis.device_type.upper()}] {analysis.mac}")
            print(f"  Confidence: {analysis.old_confidence} → {analysis.new_confidence}")
            print(f"  Sightings: {analysis.sighting_count}, Avg RSSI: {avg_rssi_str}")
            print(f"  Presence ratio: {analysis.presence_ratio:.1%} (active: {analysis.active_presence_ratio:.1%})" if analysis.active_presence_ratio is not None else f"  Presence ratio: {analysis.presence_ratio:.1%}")
            print(f"  Boundaries: early={analysis.early_presence}, late={analysis.late_presence}")
            # RSSI trend
            if analysis.rssi_std_dev is not None:
                peak_str = " ⬆⬇ PEAK" if analysis.rssi_has_peak else ""
                print(f"  RSSI σ={analysis.rssi_std_dev:.1f} dBm{peak_str}")
            # MAC randomization
            if analysis.is_randomized_mac:
                print(f"  MAC: randomized (locally-administered)")
            # GPS spread
            if analysis.gps_spread_meters is not None:
                print(f"  GPS spread: {analysis.gps_spread_meters:.0f}m from centroid")
            # Scanner count
            if analysis.scanner_count > 1:
                print(f"  Scanners: {analysis.scanner_count}")
            # Burstiness
            if analysis.burstiness_cov is not None:
                print(f"  Burstiness CoV: {analysis.burstiness_cov:.2f}")
            # SAR role classification
            if analysis.sar_role:
                print(f"  *** {analysis.sar_role} ***")
            # Show enrichment for WiFi devices
            if analysis.device_type == "wifi":
                if analysis.vendor_name:
                    print(f"  Vendor (OUI): {analysis.vendor_name}")
                if analysis.guessed_type:
                    print(f"  Device Type (guess): {analysis.guessed_type}")
                if analysis.ssid_count > 0:
                    ssids_preview = ', '.join(analysis.ssid_list[:5])
                    extra = f" (+{analysis.ssid_count - 5} more)" if analysis.ssid_count > 5 else ""
                    print(f"  SSIDs probed ({analysis.ssid_count}): {ssids_preview}{extra}")
                if analysis.is_beacon_device is True:
                    print(f"  Packet type: Beacon (Access Point)")
                elif analysis.is_beacon_device is False:
                    print(f"  Packet type: ProbeRequest (client)")
            # BT device name/manufacturer
            if analysis.device_type == "bt":
                if analysis.device_name:
                    print(f"  BT Name: {analysis.device_name}")
                if analysis.manufacturer_name:
                    print(f"  BT Manufacturer: {analysis.manufacturer_name}")
                if analysis.guessed_type:
                    print(f"  Device Type: {analysis.guessed_type}")
            if analysis.factors:
                print("  Factors:")
                for f in analysis.factors:
                    print(f"    - {f}")
    
    # Summary stats
    summary = analyzer.get_summary()
    
    print(f"\n{'='*60}")
    print("Analysis Summary:")
    print(f"{'='*60}")
    print(f"  Total devices analyzed: {len(analyses)}")
    print(f"  High confidence (≥70): {summary['devices']['high_confidence']}")
    print(f"  Low confidence (≤30): {summary['devices']['low_confidence']}")
    print(f"  Randomized MACs: {summary['devices'].get('randomized_macs', 0)}")
    print(f"  Beacon devices (APs): {summary['devices'].get('beacon_devices', 0)}")
    print(f"  RSSI peaks detected: {summary['devices'].get('rssi_peak_detected', 0)}")
    
    if summary.get('high_confidence_devices'):
        print(f"\n  Top candidates (high confidence):")
        for d in summary['high_confidence_devices']:
            print(f"    - [{d['type'].upper()}] {d['mac']}: {d['confidence']}")
    
    # Apply updates
    if not dry_run:
        print(f"\n{'='*60}")
        print("Applying updates to database...")
        result = analyzer.apply_updates()
        print(f"  Updated {result['bt_updated']} BT devices")
        print(f"  Updated {result['wifi_updated']} WiFi devices")
        print(f"  Enriched {result.get('wifi_enriched', 0)} WiFi devices with vendor/type info")
        print("Done!")
        summary["updates"] = result
    else:
        print(f"\n[DRY RUN] No changes applied to database.")
        summary["updates"] = {"bt_updated": 0, "wifi_updated": 0, "wifi_enriched": 0, "dry_run": True}
    
    return summary


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze device confidence for SAR operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python confidence_analyzer.py              # Run analysis and update DB
  python confidence_analyzer.py --dry-run    # Preview without changes
  python confidence_analyzer.py -v           # Verbose output
  python confidence_analyzer.py --dry-run -v # Full preview

Confidence Scale:
  0-30:   Likely SAR team equipment
  31-69:  Uncertain
  70-100: Possible missing person's device
        """
    )
    
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview analysis without modifying database"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed analysis for each device"
    )
    
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompt"
    )
    
    args = parser.parse_args()
    
    # Confirmation prompt unless --yes or --dry-run
    if not args.dry_run and not args.yes:
        print("\nThis will recalculate confidence scores for all devices in the database.")
        response = input("Continue? [y/N]: ").strip().lower()
        if response != 'y':
            print("Aborted.")
            sys.exit(0)
    
    result = run_analysis(dry_run=args.dry_run, verbose=args.verbose)
    
    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
