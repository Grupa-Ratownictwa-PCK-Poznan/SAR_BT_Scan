#!/usr/bin/env python3
"""
Device Triangulation and Movement Analysis Module (v2)

Analyzes all sightings for a specific device (by MAC address) to:
- Triangulate location based on GPS coordinates, signal strength, and HDOP quality
- Determine if the device is stationary or moving
- Estimate travel direction (heading) and predict future location
- Generate a timeline of movement with altitude analysis

Can be run as:
- CLI: python triangulation.py <MAC> [--json]
- Module: from triangulation import DeviceTriangulator

Author: SAR BT Scanner Team
"""

import argparse
import json
import math
import sys
import os
import time as _time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from statistics import mean, stdev, median

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from storage import db, DB_PATH


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Sighting:
    """A single device sighting (observation)."""
    timestamp: int
    lat: Optional[float]
    lon: Optional[float]
    rssi: Optional[int]
    source: str  # 'bt' or 'wifi'
    ssid: Optional[str] = None       # For WiFi only
    name: Optional[str] = None       # For BT only
    scanner: Optional[str] = None
    gps_hdop: Optional[float] = None # GPS horizontal dilution of precision
    tx_power: Optional[int] = None   # BT transmit power (dBm)
    alt: Optional[float] = None      # Altitude (meters)
    is_outlier: bool = False         # Flagged by outlier filter

    @property
    def has_location(self) -> bool:
        return self.lat is not None and self.lon is not None

    @property
    def has_altitude(self) -> bool:
        return self.alt is not None


@dataclass
class LocationCluster:
    """A cluster of sightings at a similar location."""
    center_lat: float
    center_lon: float
    sightings: List[Sighting] = field(default_factory=list)
    avg_rssi: Optional[float] = None
    avg_hdop: Optional[float] = None
    avg_alt: Optional[float] = None
    first_seen: Optional[int] = None
    last_seen: Optional[int] = None
    duration_seconds: int = 0

    def update_stats(self):
        """Update cluster statistics."""
        if not self.sightings:
            return
        rssi_values = [s.rssi for s in self.sightings if s.rssi is not None]
        if rssi_values:
            self.avg_rssi = mean(rssi_values)
        hdop_values = [s.gps_hdop for s in self.sightings if s.gps_hdop is not None]
        if hdop_values:
            self.avg_hdop = mean(hdop_values)
        alt_values = [s.alt for s in self.sightings if s.alt is not None]
        if alt_values:
            self.avg_alt = mean(alt_values)
        timestamps = [s.timestamp for s in self.sightings]
        self.first_seen = min(timestamps)
        self.last_seen = max(timestamps)
        self.duration_seconds = self.last_seen - self.first_seen


@dataclass
class MovementSegment:
    """A segment of movement between locations."""
    from_lat: float
    from_lon: float
    to_lat: float
    to_lon: float
    start_time: int
    end_time: int
    distance_meters: float
    speed_mps: float  # meters per second
    heading_degrees: Optional[float] = None  # Compass bearing (0=N, 90=E, …)

    @property
    def speed_kmh(self) -> float:
        return self.speed_mps * 3.6


@dataclass
class TriangulationResult:
    """Complete triangulation analysis result."""
    mac: str
    device_type: str  # 'bt', 'wifi', or 'both'
    first_seen: Optional[int] = None
    last_seen: Optional[int] = None
    total_sightings: int = 0
    sightings_with_location: int = 0

    # Device info
    name: Optional[str] = None
    manufacturer: Optional[str] = None
    vendor: Optional[str] = None
    confidence: Optional[int] = None
    notes: Optional[str] = None
    ssids: List[str] = field(default_factory=list)

    # Location analysis
    is_stationary: bool = True
    movement_confidence: float = 0.0  # 0-100
    estimated_location: Optional[Tuple[float, float]] = None
    last_known_location: Optional[Tuple[float, float]] = None
    location_clusters: List[LocationCluster] = field(default_factory=list)
    movement_segments: List[MovementSegment] = field(default_factory=list)

    # Predicted location (extrapolation for moving devices)
    predicted_location: Optional[Tuple[float, float]] = None
    predicted_uncertainty_meters: Optional[float] = None
    predicted_elapsed_seconds: Optional[int] = None
    last_known_heading: Optional[float] = None

    # Statistics
    total_distance_meters: float = 0.0
    avg_speed_mps: float = 0.0
    max_speed_mps: float = 0.0
    observation_duration_seconds: int = 0
    area_covered_sq_meters: float = 0.0

    # Altitude
    altitude_min: Optional[float] = None
    altitude_max: Optional[float] = None
    altitude_delta: Optional[float] = None
    sightings_with_altitude: int = 0

    # Quality / filtering
    outliers_filtered: int = 0

    # Path data for visualization
    path_points: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        d = {
            'mac': self.mac,
            'device_type': self.device_type,
            'first_seen': self.first_seen,
            'first_seen_str': datetime.fromtimestamp(self.first_seen).isoformat() if self.first_seen else None,
            'last_seen': self.last_seen,
            'last_seen_str': datetime.fromtimestamp(self.last_seen).isoformat() if self.last_seen else None,
            'total_sightings': self.total_sightings,
            'sightings_with_location': self.sightings_with_location,
            'name': self.name,
            'manufacturer': self.manufacturer,
            'vendor': self.vendor,
            'confidence': self.confidence,
            'notes': self.notes,
            'ssids': self.ssids,
            'is_stationary': self.is_stationary,
            'movement_confidence': round(self.movement_confidence, 1),
            'movement_status': 'stationary' if self.is_stationary else 'moving',
            'estimated_location': {
                'lat': self.estimated_location[0],
                'lon': self.estimated_location[1]
            } if self.estimated_location else None,
            'last_known_location': {
                'lat': self.last_known_location[0],
                'lon': self.last_known_location[1]
            } if self.last_known_location else None,
            'predicted_location': {
                'lat': self.predicted_location[0],
                'lon': self.predicted_location[1],
                'uncertainty_meters': round(self.predicted_uncertainty_meters, 1) if self.predicted_uncertainty_meters else None,
                'elapsed_seconds': self.predicted_elapsed_seconds,
                'elapsed_str': format_duration(self.predicted_elapsed_seconds) if self.predicted_elapsed_seconds else None,
            } if self.predicted_location else None,
            'last_known_heading': round(self.last_known_heading, 1) if self.last_known_heading is not None else None,
            'last_known_heading_cardinal': _degrees_to_cardinal(self.last_known_heading) if self.last_known_heading is not None else None,
            'total_distance_meters': round(self.total_distance_meters, 2),
            'avg_speed_mps': round(self.avg_speed_mps, 2),
            'avg_speed_kmh': round(self.avg_speed_mps * 3.6, 2),
            'max_speed_mps': round(self.max_speed_mps, 2),
            'max_speed_kmh': round(self.max_speed_mps * 3.6, 2),
            'observation_duration_seconds': self.observation_duration_seconds,
            'observation_duration_str': format_duration(self.observation_duration_seconds),
            'area_covered_sq_meters': round(self.area_covered_sq_meters, 2),
            'altitude_min': round(self.altitude_min, 1) if self.altitude_min is not None else None,
            'altitude_max': round(self.altitude_max, 1) if self.altitude_max is not None else None,
            'altitude_delta': round(self.altitude_delta, 1) if self.altitude_delta is not None else None,
            'sightings_with_altitude': self.sightings_with_altitude,
            'outliers_filtered': self.outliers_filtered,
            'location_clusters': [
                {
                    'center_lat': c.center_lat,
                    'center_lon': c.center_lon,
                    'sighting_count': len(c.sightings),
                    'avg_rssi': round(c.avg_rssi, 1) if c.avg_rssi else None,
                    'avg_hdop': round(c.avg_hdop, 2) if c.avg_hdop else None,
                    'avg_alt': round(c.avg_alt, 1) if c.avg_alt is not None else None,
                    'first_seen': c.first_seen,
                    'first_seen_str': datetime.fromtimestamp(c.first_seen).isoformat() if c.first_seen else None,
                    'last_seen': c.last_seen,
                    'last_seen_str': datetime.fromtimestamp(c.last_seen).isoformat() if c.last_seen else None,
                    'duration_seconds': c.duration_seconds
                }
                for c in self.location_clusters
            ],
            'movement_segments': [
                {
                    'from_lat': s.from_lat,
                    'from_lon': s.from_lon,
                    'to_lat': s.to_lat,
                    'to_lon': s.to_lon,
                    'start_time': s.start_time,
                    'start_time_str': datetime.fromtimestamp(s.start_time).isoformat(),
                    'end_time': s.end_time,
                    'end_time_str': datetime.fromtimestamp(s.end_time).isoformat(),
                    'distance_meters': round(s.distance_meters, 2),
                    'speed_mps': round(s.speed_mps, 2),
                    'speed_kmh': round(s.speed_kmh, 2),
                    'heading_degrees': round(s.heading_degrees, 1) if s.heading_degrees is not None else None,
                    'heading_cardinal': _degrees_to_cardinal(s.heading_degrees) if s.heading_degrees is not None else None,
                }
                for s in self.movement_segments
            ],
            'path_points': self.path_points
        }
        return d


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def format_duration(seconds: int) -> str:
    """Format duration in human-readable form."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the distance between two points on Earth using Haversine formula.

    Returns distance in meters.
    """
    R = 6371000  # Earth's radius in meters

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the initial compass bearing from point 1 to point 2.

    Returns bearing in degrees (0 = North, 90 = East, 180 = South, 270 = West).
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_lambda = math.radians(lon2 - lon1)

    x = math.sin(d_lambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - \
        math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda)

    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360


def destination_point(lat: float, lon: float, bearing_deg: float, distance_m: float) -> Tuple[float, float]:
    """Calculate the destination point given start, bearing (degrees), and distance (meters).

    Uses the spherical-earth forward-azimuth formula.
    """
    R = 6371000.0
    d = distance_m / R
    brng = math.radians(bearing_deg)

    phi1 = math.radians(lat)
    lam1 = math.radians(lon)

    phi2 = math.asin(
        math.sin(phi1) * math.cos(d) +
        math.cos(phi1) * math.sin(d) * math.cos(brng)
    )
    lam2 = lam1 + math.atan2(
        math.sin(brng) * math.sin(d) * math.cos(phi1),
        math.cos(d) - math.sin(phi1) * math.sin(phi2)
    )

    return (math.degrees(phi2), math.degrees(lam2))


def _degrees_to_cardinal(deg: Optional[float]) -> Optional[str]:
    """Convert compass degrees to cardinal direction label."""
    if deg is None:
        return None
    dirs = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
            'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    ix = round(deg / 22.5) % 16
    return dirs[ix]


def estimate_distance_from_rssi(rssi: int, tx_power: int = -59) -> float:
    """Estimate distance from RSSI using path-loss model.

    Uses free-space path loss model with typical outdoor parameters.
    Returns estimated distance in meters.
    """
    # Path loss exponent (2 for free space, 2.5-4 for indoor)
    n = 2.5

    if rssi >= tx_power:
        return 1.0  # Very close

    ratio = (tx_power - rssi) / (10 * n)
    return 10 ** ratio


def convex_hull_area_sq_m(points: List[Tuple[float, float]]) -> float:
    """Calculate the area (sq meters) of the convex hull of a set of (lat, lon) points.

    Uses Andrew's monotone-chain algorithm for the hull and the
    Shoelace formula for the area, with lat/lon → meter conversion.
    Falls back to bounding-box if fewer than 3 unique points.
    """
    if len(points) < 3:
        return _bounding_box_area(points)

    # Convert to local meters (relative to centroid) for area calculation
    avg_lat = mean(p[0] for p in points)
    avg_lon = mean(p[1] for p in points)
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(avg_lat))

    pts_m = [(
        (p[0] - avg_lat) * m_per_deg_lat,
        (p[1] - avg_lon) * m_per_deg_lon
    ) for p in points]

    # Remove duplicates
    pts_m = list(set(pts_m))
    if len(pts_m) < 3:
        return _bounding_box_area(points)

    # Andrew's monotone chain
    pts_m.sort()

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts_m:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts_m):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    hull = lower[:-1] + upper[:-1]
    if len(hull) < 3:
        return _bounding_box_area(points)

    # Shoelace formula
    n = len(hull)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += hull[i][0] * hull[j][1]
        area -= hull[j][0] * hull[i][1]
    return abs(area) / 2.0


def _bounding_box_area(points: List[Tuple[float, float]]) -> float:
    """Fallback bounding-box area in sq meters."""
    if not points:
        return 0.0
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    avg_lat = mean(lats)
    m_lat = 111320.0
    m_lon = 111320.0 * math.cos(math.radians(avg_lat))
    return (max(lats) - min(lats)) * m_lat * (max(lons) - min(lons)) * m_lon


# ---------------------------------------------------------------------------
# Main analyser class
# ---------------------------------------------------------------------------

class DeviceTriangulator:
    """Main triangulation and movement analysis class."""

    # Clustering parameters
    CLUSTER_RADIUS_METERS = 30      # Sightings within this distance are in same cluster
    CLUSTER_TIME_GAP_SECONDS = 1800 # If same-location sightings are >30 min apart, split cluster
    CLUSTER_MAX_ITERATIONS = 10     # Max centroid-expansion iterations
    MIN_MOVEMENT_DISTANCE = 20      # Minimum distance (m) to consider as movement
    MIN_MOVEMENT_SPEED = 0.3        # Minimum speed (m/s) to consider as moving
    STATIONARY_MAX_AREA = 2500      # Max area (sq m) to consider device stationary

    # Outlier detection
    OUTLIER_DISTANCE_SIGMA = 3.0    # Flag sightings >3σ from median location

    # Prediction
    PREDICTION_MAX_ELAPSED = 7200   # Don't predict beyond 2 hours since last seen
    PREDICTION_UNCERTAINTY_RATE = 2.0  # Uncertainty radius grows at 2× the speed (m/s)

    def __init__(self, mac: str):
        """Initialize triangulator for a specific MAC address.

        Args:
            mac: MAC address to analyze (case-insensitive)
        """
        self.mac = mac.upper()
        self.sightings: List[Sighting] = []
        self.result: Optional[TriangulationResult] = None

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    def fetch_sightings(self) -> Tuple[str, List[Sighting]]:
        """Fetch all sightings for the device from the database.

        Returns:
            Tuple of (device_type, sightings_list)
        """
        sightings = []
        device_type = None
        device_info = {}

        with db() as con:
            # Check if this is a BT device
            cursor = con.execute(
                "SELECT addr, first_seen, last_seen, name, manufacturer, confidence, notes "
                "FROM devices WHERE addr = ? COLLATE NOCASE",
                (self.mac,)
            )
            bt_device = cursor.fetchone()

            # Check if this is a WiFi device
            cursor = con.execute(
                "SELECT mac, first_seen, last_seen, vendor, device_type, confidence, notes "
                "FROM wifi_devices WHERE mac = ? COLLATE NOCASE",
                (self.mac,)
            )
            wifi_device = cursor.fetchone()

            # Determine device type
            if bt_device and wifi_device:
                device_type = 'both'
                device_info['name'] = bt_device[3]
                device_info['manufacturer'] = bt_device[4]
                device_info['vendor'] = wifi_device[3]
                device_info['wifi_device_type'] = wifi_device[4]
                device_info['confidence'] = max(bt_device[5] or 0, wifi_device[5] or 0)
                device_info['notes'] = bt_device[6] or wifi_device[6] or ''
            elif bt_device:
                device_type = 'bt'
                device_info['name'] = bt_device[3]
                device_info['manufacturer'] = bt_device[4]
                device_info['confidence'] = bt_device[5]
                device_info['notes'] = bt_device[6] or ''
            elif wifi_device:
                device_type = 'wifi'
                device_info['vendor'] = wifi_device[3]
                device_info['wifi_device_type'] = wifi_device[4]
                device_info['confidence'] = wifi_device[5]
                device_info['notes'] = wifi_device[6] or ''
            else:
                return None, []

            self.device_info = device_info

            # ----- Fetch BT sightings (now including gps_hdop, tx_power, alt) -----
            if device_type in ('bt', 'both'):
                cursor = con.execute(
                    "SELECT ts_unix, lat, lon, rssi, local_name, scanner_name, "
                    "       gps_hdop, tx_power, alt "
                    "FROM sightings WHERE addr = ? COLLATE NOCASE "
                    "ORDER BY ts_unix ASC",
                    (self.mac,)
                )
                for row in cursor.fetchall():
                    ts, lat, lon, rssi, name, scanner, hdop, txp, alt = row
                    sightings.append(Sighting(
                        timestamp=ts,
                        lat=lat,
                        lon=lon,
                        rssi=rssi,
                        source='bt',
                        name=name,
                        scanner=scanner,
                        gps_hdop=hdop,
                        tx_power=txp,
                        alt=alt,
                    ))

            # ----- Fetch WiFi sightings (including alt if available) -----
            if device_type in ('wifi', 'both'):
                # Check available columns (older schema may lack some)
                cursor = con.execute("PRAGMA table_info(wifi_associations)")
                columns = [row[1] for row in cursor.fetchall()]
                has_scanner = 'scanner_name' in columns
                has_alt = 'alt' in columns

                select_cols = "ts_unix, lat, lon, rssi, ssid"
                if has_scanner:
                    select_cols += ", scanner_name"
                if has_alt:
                    select_cols += ", alt"

                query = (
                    f"SELECT {select_cols} "
                    "FROM wifi_associations WHERE mac = ? COLLATE NOCASE "
                    "ORDER BY ts_unix ASC"
                )

                cursor = con.execute(query, (self.mac,))
                for row in cursor.fetchall():
                    idx = 0
                    ts, lat, lon, rssi, ssid = row[0], row[1], row[2], row[3], row[4]
                    idx = 5
                    scanner = row[idx] if has_scanner else None
                    if has_scanner:
                        idx += 1
                    alt = row[idx] if has_alt else None

                    sightings.append(Sighting(
                        timestamp=ts,
                        lat=lat,
                        lon=lon,
                        rssi=rssi,
                        source='wifi',
                        ssid=ssid,
                        scanner=scanner,
                        alt=alt,
                    ))

                # Get unique SSIDs
                cursor = con.execute(
                    "SELECT DISTINCT ssid FROM wifi_associations "
                    "WHERE mac = ? COLLATE NOCASE AND ssid IS NOT NULL",
                    (self.mac,)
                )
                device_info['ssids'] = [row[0] for row in cursor.fetchall()]

        # Sort by timestamp
        sightings.sort(key=lambda s: s.timestamp)
        self.sightings = sightings

        return device_type, sightings

    # ------------------------------------------------------------------
    # Outlier filtering  (#9)
    # ------------------------------------------------------------------

    def filter_outliers(self, sightings: List[Sighting]) -> int:
        """Flag GPS outlier sightings using median absolute deviation.

        Sightings whose distance from the median lat/lon exceeds
        OUTLIER_DISTANCE_SIGMA * MAD are flagged (is_outlier=True)
        but NOT removed, so the caller can decide.

        Returns the number of sightings flagged.
        """
        with_loc = [s for s in sightings if s.has_location]
        if len(with_loc) < 5:
            return 0  # Too few points to detect outliers

        med_lat = median(s.lat for s in with_loc)
        med_lon = median(s.lon for s in with_loc)

        distances = [haversine_distance(s.lat, s.lon, med_lat, med_lon) for s in with_loc]
        med_dist = median(distances)
        # MAD (median absolute deviation) scaled to approximate σ
        mad = median(abs(d - med_dist) for d in distances)
        if mad < 1.0:
            mad = 1.0  # Prevent degenerate case
        sigma_approx = mad * 1.4826  # MAD → σ conversion factor

        threshold = self.OUTLIER_DISTANCE_SIGMA * sigma_approx
        flagged = 0
        for s, d in zip(with_loc, distances):
            if d > threshold:
                s.is_outlier = True
                flagged += 1

        return flagged

    # ------------------------------------------------------------------
    # Clustering  (#3: temporal, #4: centroid expansion, #1: HDOP + #2: tx_power weighting)
    # ------------------------------------------------------------------

    def cluster_locations(self, sightings: List[Sighting]) -> List[LocationCluster]:
        """Group sightings into spatio-temporal location clusters.

        Improvements over v1:
        - Temporal splitting: same-location sightings separated by
          CLUSTER_TIME_GAP_SECONDS are placed in different clusters
          (reveals "returned to location" patterns).
        - Iterative centroid expansion: after initial assignment the
          centroid is recalculated and unassigned nearby points are
          re-checked until stable.
        - Weighting uses RSSI, GPS HDOP, and per-sighting tx_power for
          more accurate center calculation.
        """
        sightings_with_loc = [
            s for s in sightings
            if s.has_location and not s.is_outlier
        ]
        if not sightings_with_loc:
            return []

        # Sort chronologically for temporal splitting
        sightings_with_loc.sort(key=lambda s: s.timestamp)

        clusters: List[LocationCluster] = []
        assigned: set = set()

        for i, seed in enumerate(sightings_with_loc):
            if i in assigned:
                continue

            # ---- Initial assignment: spatial + temporal ----
            cluster_indices = [i]
            assigned.add(i)

            for j, other in enumerate(sightings_with_loc):
                if j in assigned:
                    continue

                dist = haversine_distance(seed.lat, seed.lon, other.lat, other.lon)
                if dist > self.CLUSTER_RADIUS_METERS:
                    continue

                # Temporal check: gap from nearest already-assigned sighting
                min_time_gap = min(
                    abs(other.timestamp - sightings_with_loc[k].timestamp)
                    for k in cluster_indices
                )
                if min_time_gap > self.CLUSTER_TIME_GAP_SECONDS:
                    continue  # Same place but too far apart in time → separate cluster

                cluster_indices.append(j)
                assigned.add(j)

            # ---- Iterative centroid expansion ----
            for _iter in range(self.CLUSTER_MAX_ITERATIONS):
                cluster_sightings = [sightings_with_loc[k] for k in cluster_indices]
                center_lat, center_lon = self._weighted_center(cluster_sightings)

                # Check for unassigned points near the new centroid
                expanded = False
                for j, other in enumerate(sightings_with_loc):
                    if j in assigned:
                        continue
                    dist = haversine_distance(center_lat, center_lon, other.lat, other.lon)
                    if dist > self.CLUSTER_RADIUS_METERS:
                        continue
                    min_time_gap = min(
                        abs(other.timestamp - sightings_with_loc[k].timestamp)
                        for k in cluster_indices
                    )
                    if min_time_gap > self.CLUSTER_TIME_GAP_SECONDS:
                        continue
                    cluster_indices.append(j)
                    assigned.add(j)
                    expanded = True

                if not expanded:
                    break  # Stable — no new points absorbed

            # ---- Build cluster ----
            cluster_sightings = [sightings_with_loc[k] for k in cluster_indices]
            center_lat, center_lon = self._weighted_center(cluster_sightings)

            cluster = LocationCluster(
                center_lat=center_lat,
                center_lon=center_lon,
                sightings=cluster_sightings,
            )
            cluster.update_stats()
            clusters.append(cluster)

        # Sort clusters by first seen time
        clusters.sort(key=lambda c: c.first_seen or 0)
        return clusters

    def _weighted_center(self, sightings: List[Sighting]) -> Tuple[float, float]:
        """Compute the weighted centroid of sightings.

        Weights combine:
        - RSSI strength (higher = more accurate position)
        - 1/HDOP (lower HDOP = better GPS accuracy)
        - tx_power-adjusted RSSI distance if tx_power available
        """
        weights = []
        for s in sightings:
            w = 1.0

            # RSSI weight: stronger signal → closer → more positional weight
            if s.rssi is not None:
                w *= max(1, 100 + s.rssi)  # e.g. RSSI=-60 → weight 40

            # HDOP weight: lower HDOP → better GPS fix → more weight
            if s.gps_hdop is not None and s.gps_hdop > 0:
                w *= (1.0 / s.gps_hdop)

            # If tx_power is known, factor in the estimated distance
            if s.tx_power is not None and s.rssi is not None:
                est_dist = estimate_distance_from_rssi(s.rssi, s.tx_power)
                # Closer estimated distance → more weight (inverse)
                w *= (1.0 / max(1.0, est_dist))

            weights.append(w)

        total_w = sum(weights)
        if total_w == 0:
            total_w = 1.0

        center_lat = sum(s.lat * w for s, w in zip(sightings, weights)) / total_w
        center_lon = sum(s.lon * w for s, w in zip(sightings, weights)) / total_w
        return center_lat, center_lon

    # ------------------------------------------------------------------
    # Movement analysis  (#6: heading, #10: convex hull)
    # ------------------------------------------------------------------

    def analyze_movement(self, clusters: List[LocationCluster]) -> Tuple[bool, float, List[MovementSegment]]:
        """Analyze movement between location clusters.

        Returns:
            Tuple of (is_stationary, confidence, movement_segments)
        """
        if len(clusters) < 2:
            # Single location or no data - stationary by default
            return True, 90.0, []

        segments = []
        total_distance = 0
        speeds = []

        for i in range(len(clusters) - 1):
            c1 = clusters[i]
            c2 = clusters[i + 1]

            distance = haversine_distance(
                c1.center_lat, c1.center_lon,
                c2.center_lat, c2.center_lon
            )

            # Time between cluster centers
            time_diff = (c2.first_seen or 0) - (c1.last_seen or 0)
            if time_diff <= 0:
                time_diff = 1  # Avoid division by zero

            speed = distance / time_diff

            # Heading (bearing) between clusters
            heading = calculate_bearing(
                c1.center_lat, c1.center_lon,
                c2.center_lat, c2.center_lon
            )

            segment = MovementSegment(
                from_lat=c1.center_lat,
                from_lon=c1.center_lon,
                to_lat=c2.center_lat,
                to_lon=c2.center_lon,
                start_time=c1.last_seen or 0,
                end_time=c2.first_seen or 0,
                distance_meters=distance,
                speed_mps=speed,
                heading_degrees=heading,
            )
            segments.append(segment)

            if distance >= self.MIN_MOVEMENT_DISTANCE:
                total_distance += distance
                speeds.append(speed)

        # Calculate area covered — convex hull (#10)
        all_points = [(c.center_lat, c.center_lon) for c in clusters]
        area_sq_m = convex_hull_area_sq_m(all_points)

        # Determine if stationary
        avg_speed = mean(speeds) if speeds else 0
        max_speed = max(speeds) if speeds else 0

        # Score movement indicators (0-100 for each)
        distance_score = min(100, total_distance / 10)   # 1000m = 100
        area_score = min(100, area_sq_m / 100)            # 10000 sq m = 100
        speed_score = min(100, avg_speed * 20)            # 5 m/s = 100

        movement_score = (distance_score + area_score + speed_score) / 3

        is_stationary = (
            total_distance < 100 and
            area_sq_m < self.STATIONARY_MAX_AREA and
            avg_speed < self.MIN_MOVEMENT_SPEED
        )

        # Calculate confidence
        if is_stationary:
            confidence = 100 - movement_score
        else:
            confidence = movement_score

        confidence = max(30, min(95, confidence))

        # Store for later
        self._total_distance = total_distance
        self._area_sq_m = area_sq_m
        self._avg_speed = avg_speed
        self._max_speed = max_speed

        return is_stationary, confidence, segments

    # ------------------------------------------------------------------
    # Primary location  (#5: movement-aware)
    # ------------------------------------------------------------------

    def estimate_primary_location(
        self,
        clusters: List[LocationCluster],
        is_stationary: bool,
    ) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]]:
        """Estimate the most likely device location and last known location.

        For stationary devices: best cluster (most sightings + strongest RSSI).
        For moving devices: most recent cluster.

        Returns:
            (estimated_location, last_known_location) — both (lat, lon) or None
        """
        if not clusters:
            return None, None

        # Last known is always the most recent cluster
        last_cluster = clusters[-1]
        last_known = (last_cluster.center_lat, last_cluster.center_lon)

        if is_stationary:
            # Best cluster by sighting count weighted by RSSI
            best_cluster = max(
                clusters,
                key=lambda c: len(c.sightings) * (1 + (c.avg_rssi + 100) / 100 if c.avg_rssi else 1)
            )
            estimated = (best_cluster.center_lat, best_cluster.center_lon)
        else:
            # For moving device, estimated = last known
            estimated = last_known

        return estimated, last_known

    # ------------------------------------------------------------------
    # Predicted location  (#7)
    # ------------------------------------------------------------------

    def predict_location(
        self,
        segments: List[MovementSegment],
        last_known: Optional[Tuple[float, float]],
        last_seen: Optional[int],
        avg_speed: float,
        is_stationary: bool,
    ) -> Tuple[Optional[Tuple[float, float]], Optional[float], Optional[int], Optional[float]]:
        """Project where the device might be NOW based on last known movement.

        For stationary devices: no prediction (returns Nones).
        For moving devices: extrapolates from last known location using
        last heading and average speed.

        Returns:
            (predicted_lat_lon, uncertainty_meters, elapsed_seconds, heading)
        """
        if is_stationary or not last_known or not last_seen:
            return None, None, None, None

        now_ts = int(_time.time())
        elapsed = now_ts - last_seen
        if elapsed < 0 or elapsed > self.PREDICTION_MAX_ELAPSED:
            return None, None, None, None

        # Determine last heading
        if segments:
            last_heading = segments[-1].heading_degrees
            # Use speed from last segment if it's significant; else fall back to avg
            last_speed = segments[-1].speed_mps
            if last_speed < 0.1:
                last_speed = avg_speed
        else:
            return None, None, None, None

        if last_speed < 0.05:
            return None, None, None, None

        projected_distance = last_speed * elapsed
        pred_lat, pred_lon = destination_point(
            last_known[0], last_known[1],
            last_heading, projected_distance
        )

        uncertainty = projected_distance * self.PREDICTION_UNCERTAINTY_RATE
        # Minimum uncertainty floor
        uncertainty = max(uncertainty, 50.0)

        return (pred_lat, pred_lon), uncertainty, elapsed, last_heading

    # ------------------------------------------------------------------
    # Altitude analysis  (#8)
    # ------------------------------------------------------------------

    @staticmethod
    def compute_altitude_stats(sightings: List[Sighting]) -> Dict[str, Any]:
        """Compute altitude statistics from sightings that have altitude data.

        Returns dict with keys: min, max, delta, count
        """
        alts = [s.alt for s in sightings if s.has_altitude]
        if not alts:
            return {'min': None, 'max': None, 'delta': None, 'count': 0}
        return {
            'min': min(alts),
            'max': max(alts),
            'delta': max(alts) - min(alts),
            'count': len(alts),
        }

    # ------------------------------------------------------------------
    # Path points for visualisation
    # ------------------------------------------------------------------

    def generate_path_points(self) -> List[Dict[str, Any]]:
        """Generate path points for visualization on a map."""
        sightings_with_loc = [
            s for s in self.sightings
            if s.has_location and not s.is_outlier
        ]

        path_points = []
        for s in sightings_with_loc:
            point = {
                'lat': s.lat,
                'lon': s.lon,
                'timestamp': s.timestamp,
                'timestamp_str': datetime.fromtimestamp(s.timestamp).isoformat(),
                'time_display': datetime.fromtimestamp(s.timestamp).strftime('%H:%M:%S'),
                'rssi': s.rssi,
                'source': s.source,
                'ssid': s.ssid,
                'name': s.name,
            }
            if s.alt is not None:
                point['alt'] = round(s.alt, 1)
            if s.gps_hdop is not None:
                point['hdop'] = round(s.gps_hdop, 2)
            path_points.append(point)

        return path_points

    # ------------------------------------------------------------------
    # Main analysis pipeline
    # ------------------------------------------------------------------

    def analyze(self) -> Optional[TriangulationResult]:
        """Run full triangulation and movement analysis.

        Pipeline:
        1. Fetch sightings (BT + WiFi) with HDOP, tx_power, alt
        2. Filter GPS outliers
        3. Cluster locations (spatio-temporal, iterative centroid)
        4. Analyze movement (heading, convex-hull area)
        5. Estimate primary & last-known location (movement-aware)
        6. Predict current location (extrapolation)
        7. Compute altitude statistics

        Returns:
            TriangulationResult or None if device not found
        """
        # 1. Fetch data
        device_type, sightings = self.fetch_sightings()

        if device_type is None:
            return None

        # Initialize result
        result = TriangulationResult(
            mac=self.mac,
            device_type=device_type
        )

        # Populate device info
        result.name = self.device_info.get('name')
        result.manufacturer = self.device_info.get('manufacturer')
        result.vendor = self.device_info.get('vendor')
        result.confidence = self.device_info.get('confidence')
        result.notes = self.device_info.get('notes')
        result.ssids = self.device_info.get('ssids', [])

        # Basic stats
        result.total_sightings = len(sightings)
        result.sightings_with_location = sum(1 for s in sightings if s.has_location)

        if sightings:
            result.first_seen = sightings[0].timestamp
            result.last_seen = sightings[-1].timestamp
            result.observation_duration_seconds = result.last_seen - result.first_seen

        # 2. Outlier filtering
        result.outliers_filtered = self.filter_outliers(sightings)

        # 3. Cluster locations (spatio-temporal)
        clusters = self.cluster_locations(sightings)
        result.location_clusters = clusters

        # 4. Analyze movement
        is_stationary, confidence, segments = self.analyze_movement(clusters)
        result.is_stationary = is_stationary
        result.movement_confidence = confidence
        result.movement_segments = segments

        # Movement statistics
        result.total_distance_meters = getattr(self, '_total_distance', 0)
        result.area_covered_sq_meters = getattr(self, '_area_sq_m', 0)
        result.avg_speed_mps = getattr(self, '_avg_speed', 0)
        result.max_speed_mps = getattr(self, '_max_speed', 0)

        # 5. Estimate primary & last-known location
        estimated, last_known = self.estimate_primary_location(clusters, is_stationary)
        result.estimated_location = estimated
        result.last_known_location = last_known

        # Last known heading (from final movement segment)
        if segments:
            result.last_known_heading = segments[-1].heading_degrees

        # 6. Predicted location
        pred_loc, pred_unc, pred_elapsed, _heading = self.predict_location(
            segments, last_known, result.last_seen,
            result.avg_speed_mps, is_stationary,
        )
        result.predicted_location = pred_loc
        result.predicted_uncertainty_meters = pred_unc
        result.predicted_elapsed_seconds = pred_elapsed

        # 7. Altitude analysis
        alt_stats = self.compute_altitude_stats(sightings)
        result.altitude_min = alt_stats['min']
        result.altitude_max = alt_stats['max']
        result.altitude_delta = alt_stats['delta']
        result.sightings_with_altitude = alt_stats['count']

        # Path points
        result.path_points = self.generate_path_points()

        self.result = result
        return result

    # ------------------------------------------------------------------
    # CLI output
    # ------------------------------------------------------------------

    def print_summary(self):
        """Print a text summary to console."""
        if not self.result:
            print(f"No data found for device: {self.mac}")
            return

        r = self.result

        print("=" * 60)
        print("DEVICE TRIANGULATION ANALYSIS (v2)")
        print("=" * 60)
        print()

        # Device info
        print("DEVICE INFORMATION")
        print("-" * 40)
        print(f"  MAC Address:    {r.mac}")
        print(f"  Device Type:    {r.device_type.upper()}")

        if r.name:
            print(f"  Name:           {r.name}")
        if r.manufacturer:
            print(f"  Manufacturer:   {r.manufacturer}")
        if r.vendor:
            print(f"  Vendor:         {r.vendor}")
        if r.confidence is not None:
            print(f"  Confidence:     {r.confidence}%")

        if r.ssids:
            print(f"  SSIDs ({len(r.ssids)}):")
            for ssid in r.ssids[:5]:
                print(f"    - {ssid}")
            if len(r.ssids) > 5:
                print(f"    ... and {len(r.ssids) - 5} more")

        print()

        # Observation summary
        print("OBSERVATION SUMMARY")
        print("-" * 40)
        print(f"  Total Sightings:       {r.total_sightings}")
        print(f"  With GPS Location:     {r.sightings_with_location}")
        if r.outliers_filtered > 0:
            print(f"  Outliers Filtered:     {r.outliers_filtered}")

        if r.first_seen:
            print(f"  First Seen:            {datetime.fromtimestamp(r.first_seen).strftime('%Y-%m-%d %H:%M:%S')}")
        if r.last_seen:
            print(f"  Last Seen:             {datetime.fromtimestamp(r.last_seen).strftime('%Y-%m-%d %H:%M:%S')}")

        print(f"  Observation Duration:  {format_duration(r.observation_duration_seconds)}")

        print()

        # Movement analysis
        print("MOVEMENT ANALYSIS")
        print("-" * 40)
        status = "STATIONARY" if r.is_stationary else "MOVING"
        print(f"  Status:                {status}")
        print(f"  Confidence:            {r.movement_confidence:.1f}%")
        print(f"  Total Distance:        {r.total_distance_meters:.1f} m")
        print(f"  Area Covered:          {r.area_covered_sq_meters:.1f} sq m")
        print(f"  Average Speed:         {r.avg_speed_mps:.2f} m/s ({r.avg_speed_mps * 3.6:.2f} km/h)")
        print(f"  Maximum Speed:         {r.max_speed_mps:.2f} m/s ({r.max_speed_mps * 3.6:.2f} km/h)")

        if r.last_known_heading is not None:
            cardinal = _degrees_to_cardinal(r.last_known_heading)
            print(f"  Last Heading:          {r.last_known_heading:.1f}° ({cardinal})")

        print()

        # Altitude
        if r.sightings_with_altitude > 0:
            print("ALTITUDE ANALYSIS")
            print("-" * 40)
            print(f"  Sightings with Alt:    {r.sightings_with_altitude}")
            print(f"  Altitude Min:          {r.altitude_min:.1f} m")
            print(f"  Altitude Max:          {r.altitude_max:.1f} m")
            print(f"  Altitude Delta:        {r.altitude_delta:.1f} m")
            print()

        # Location clusters
        if r.location_clusters:
            print("LOCATION CLUSTERS")
            print("-" * 40)
            for i, cluster in enumerate(r.location_clusters, 1):
                print(f"  Cluster #{i}:")
                print(f"    Center:     ({cluster.center_lat:.6f}, {cluster.center_lon:.6f})")
                print(f"    Sightings:  {len(cluster.sightings)}")
                if cluster.avg_rssi:
                    print(f"    Avg RSSI:   {cluster.avg_rssi:.1f} dBm")
                if cluster.avg_hdop is not None:
                    print(f"    Avg HDOP:   {cluster.avg_hdop:.2f}")
                if cluster.avg_alt is not None:
                    print(f"    Avg Alt:    {cluster.avg_alt:.1f} m")
                if cluster.first_seen:
                    print(f"    First Seen: {datetime.fromtimestamp(cluster.first_seen).strftime('%H:%M:%S')}")
                if cluster.last_seen:
                    print(f"    Last Seen:  {datetime.fromtimestamp(cluster.last_seen).strftime('%H:%M:%S')}")
                print()

        # Movement segments with heading
        if r.movement_segments:
            print("MOVEMENT SEGMENTS")
            print("-" * 40)
            for i, seg in enumerate(r.movement_segments, 1):
                heading_str = ""
                if seg.heading_degrees is not None:
                    cardinal = _degrees_to_cardinal(seg.heading_degrees)
                    heading_str = f"  heading {seg.heading_degrees:.0f}° ({cardinal})"
                print(f"  #{i}: {seg.distance_meters:.0f} m @ {seg.speed_kmh:.1f} km/h{heading_str}")
            print()

        # Estimated location
        if r.estimated_location:
            print("ESTIMATED PRIMARY LOCATION")
            print("-" * 40)
            print(f"  Latitude:  {r.estimated_location[0]:.6f}")
            print(f"  Longitude: {r.estimated_location[1]:.6f}")
            print(f"  https://www.google.com/maps?q={r.estimated_location[0]},{r.estimated_location[1]}")

        # Last known location (if different from estimated)
        if r.last_known_location and r.last_known_location != r.estimated_location:
            print()
            print("LAST KNOWN LOCATION")
            print("-" * 40)
            print(f"  Latitude:  {r.last_known_location[0]:.6f}")
            print(f"  Longitude: {r.last_known_location[1]:.6f}")
            print(f"  https://www.google.com/maps?q={r.last_known_location[0]},{r.last_known_location[1]}")

        # Predicted location
        if r.predicted_location:
            print()
            print("PREDICTED CURRENT LOCATION")
            print("-" * 40)
            elapsed_str = format_duration(r.predicted_elapsed_seconds) if r.predicted_elapsed_seconds else "?"
            print(f"  Based on:  {elapsed_str} since last sighting")
            print(f"  Latitude:  {r.predicted_location[0]:.6f}")
            print(f"  Longitude: {r.predicted_location[1]:.6f}")
            if r.predicted_uncertainty_meters:
                print(f"  Uncertainty: ±{r.predicted_uncertainty_meters:.0f} m radius")
            print(f"  https://www.google.com/maps?q={r.predicted_location[0]},{r.predicted_location[1]}")

        print()
        print("=" * 60)


def analyze_device(mac: str) -> Optional[TriangulationResult]:
    """Convenience function to analyze a device by MAC address.

    Args:
        mac: MAC address to analyze

    Returns:
        TriangulationResult or None if device not found
    """
    triangulator = DeviceTriangulator(mac)
    return triangulator.analyze()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Triangulation and movement analysis for BT/WiFi devices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python triangulation.py AA:BB:CC:DD:EE:FF
  python triangulation.py AA:BB:CC:DD:EE:FF --json
  python triangulation.py AA:BB:CC:DD:EE:FF --json > result.json
        """
    )

    parser.add_argument(
        "mac",
        help="MAC address of the device to analyze"
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of formatted text"
    )

    parser.add_argument(
        "--db",
        help="Path to database file (default: uses storage.py settings)"
    )

    args = parser.parse_args()

    # Override database path if specified
    if args.db:
        import storage
        storage.DB_PATH = args.db

    # Run analysis
    triangulator = DeviceTriangulator(args.mac)
    result = triangulator.analyze()

    if result is None:
        if args.json:
            print(json.dumps({"error": f"Device not found: {args.mac}"}))
        else:
            print(f"Error: Device not found: {args.mac}")
        sys.exit(1)

    # Output
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        triangulator.print_summary()


if __name__ == "__main__":
    main()
