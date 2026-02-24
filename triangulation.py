#!/usr/bin/env python3
"""
Device Triangulation and Movement Analysis Module

Analyzes all sightings for a specific device (by MAC address) to:
- Triangulate location based on GPS coordinates and signal strength
- Determine if the device is stationary or moving
- Generate a timeline of movement

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
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from statistics import mean, stdev

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from storage import db, DB_PATH


@dataclass
class Sighting:
    """A single device sighting (observation)."""
    timestamp: int
    lat: Optional[float]
    lon: Optional[float]
    rssi: Optional[int]
    source: str  # 'bt' or 'wifi'
    ssid: Optional[str] = None  # For WiFi only
    name: Optional[str] = None  # For BT only
    scanner: Optional[str] = None
    
    @property
    def has_location(self) -> bool:
        return self.lat is not None and self.lon is not None


@dataclass
class LocationCluster:
    """A cluster of sightings at a similar location."""
    center_lat: float
    center_lon: float
    sightings: List[Sighting] = field(default_factory=list)
    avg_rssi: Optional[float] = None
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
    movement_confidence: float = 0.0  # 0-100, how confident we are about movement status
    estimated_location: Optional[Tuple[float, float]] = None
    location_clusters: List[LocationCluster] = field(default_factory=list)
    movement_segments: List[MovementSegment] = field(default_factory=list)
    
    # Statistics
    total_distance_meters: float = 0.0
    avg_speed_mps: float = 0.0
    max_speed_mps: float = 0.0
    observation_duration_seconds: int = 0
    area_covered_sq_meters: float = 0.0
    
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
            'total_distance_meters': round(self.total_distance_meters, 2),
            'avg_speed_mps': round(self.avg_speed_mps, 2),
            'avg_speed_kmh': round(self.avg_speed_mps * 3.6, 2),
            'max_speed_mps': round(self.max_speed_mps, 2),
            'max_speed_kmh': round(self.max_speed_mps * 3.6, 2),
            'observation_duration_seconds': self.observation_duration_seconds,
            'observation_duration_str': format_duration(self.observation_duration_seconds),
            'area_covered_sq_meters': round(self.area_covered_sq_meters, 2),
            'location_clusters': [
                {
                    'center_lat': c.center_lat,
                    'center_lon': c.center_lon,
                    'sighting_count': len(c.sightings),
                    'avg_rssi': round(c.avg_rssi, 1) if c.avg_rssi else None,
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
                    'speed_kmh': round(s.speed_kmh, 2)
                }
                for s in self.movement_segments
            ],
            'path_points': self.path_points
        }
        return d


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


def estimate_distance_from_rssi(rssi: int, tx_power: int = -59) -> float:
    """Estimate distance from RSSI using path-loss model.
    
    Uses free-space path loss model with typical parameters.
    Returns estimated distance in meters.
    """
    # Path loss exponent (2 for free space, 2.5-4 for indoor)
    n = 2.5
    
    if rssi >= tx_power:
        return 1.0  # Very close
    
    ratio = (tx_power - rssi) / (10 * n)
    return 10 ** ratio


class DeviceTriangulator:
    """Main triangulation and movement analysis class."""
    
    # Clustering parameters
    CLUSTER_RADIUS_METERS = 30  # Sightings within this distance are in same cluster
    MIN_MOVEMENT_DISTANCE = 20  # Minimum distance (m) to consider as movement
    MIN_MOVEMENT_SPEED = 0.3    # Minimum speed (m/s) to consider as moving
    STATIONARY_MAX_AREA = 2500  # Max area (sq m) to consider device stationary
    
    def __init__(self, mac: str):
        """Initialize triangulator for a specific MAC address.
        
        Args:
            mac: MAC address to analyze (case-insensitive)
        """
        self.mac = mac.upper()
        self.sightings: List[Sighting] = []
        self.result: Optional[TriangulationResult] = None
    
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
            
            # Fetch BT sightings
            if device_type in ('bt', 'both'):
                cursor = con.execute(
                    "SELECT ts_unix, lat, lon, rssi, local_name, scanner_name "
                    "FROM sightings WHERE addr = ? COLLATE NOCASE "
                    "ORDER BY ts_unix ASC",
                    (self.mac,)
                )
                for row in cursor.fetchall():
                    ts, lat, lon, rssi, name, scanner = row
                    sightings.append(Sighting(
                        timestamp=ts,
                        lat=lat,
                        lon=lon,
                        rssi=rssi,
                        source='bt',
                        name=name,
                        scanner=scanner
                    ))
            
            # Fetch WiFi sightings
            if device_type in ('wifi', 'both'):
                # Check if scanner_name column exists (may be missing in older schema)
                cursor = con.execute("PRAGMA table_info(wifi_associations)")
                columns = [row[1] for row in cursor.fetchall()]
                has_scanner = 'scanner_name' in columns
                
                if has_scanner:
                    query = (
                        "SELECT ts_unix, lat, lon, rssi, ssid, scanner_name "
                        "FROM wifi_associations WHERE mac = ? COLLATE NOCASE "
                        "ORDER BY ts_unix ASC"
                    )
                else:
                    query = (
                        "SELECT ts_unix, lat, lon, rssi, ssid "
                        "FROM wifi_associations WHERE mac = ? COLLATE NOCASE "
                        "ORDER BY ts_unix ASC"
                    )
                
                cursor = con.execute(query, (self.mac,))
                for row in cursor.fetchall():
                    if has_scanner:
                        ts, lat, lon, rssi, ssid, scanner = row
                    else:
                        ts, lat, lon, rssi, ssid = row
                        scanner = None
                    sightings.append(Sighting(
                        timestamp=ts,
                        lat=lat,
                        lon=lon,
                        rssi=rssi,
                        source='wifi',
                        ssid=ssid,
                        scanner=scanner
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
    
    def cluster_locations(self, sightings: List[Sighting]) -> List[LocationCluster]:
        """Group sightings into location clusters.
        
        Uses DBSCAN-like clustering based on geographic distance.
        """
        sightings_with_loc = [s for s in sightings if s.has_location]
        if not sightings_with_loc:
            return []
        
        clusters = []
        assigned = set()
        
        for i, sighting in enumerate(sightings_with_loc):
            if i in assigned:
                continue
            
            # Start a new cluster
            cluster_sightings = [sighting]
            assigned.add(i)
            
            # Find all nearby sightings
            for j, other in enumerate(sightings_with_loc):
                if j in assigned:
                    continue
                
                dist = haversine_distance(
                    sighting.lat, sighting.lon,
                    other.lat, other.lon
                )
                
                if dist <= self.CLUSTER_RADIUS_METERS:
                    cluster_sightings.append(other)
                    assigned.add(j)
            
            # Calculate cluster center (weighted by RSSI if available)
            if cluster_sightings:
                lats = [s.lat for s in cluster_sightings]
                lons = [s.lon for s in cluster_sightings]
                
                # Weight by RSSI (higher RSSI = closer = more weight)
                rssi_weights = []
                for s in cluster_sightings:
                    if s.rssi is not None:
                        # Convert RSSI to weight (higher is better, so negate and shift)
                        weight = max(1, 100 + s.rssi)
                    else:
                        weight = 1
                    rssi_weights.append(weight)
                
                total_weight = sum(rssi_weights)
                center_lat = sum(lat * w for lat, w in zip(lats, rssi_weights)) / total_weight
                center_lon = sum(lon * w for lon, w in zip(lons, rssi_weights)) / total_weight
                
                cluster = LocationCluster(
                    center_lat=center_lat,
                    center_lon=center_lon,
                    sightings=cluster_sightings
                )
                cluster.update_stats()
                clusters.append(cluster)
        
        # Sort clusters by first seen time
        clusters.sort(key=lambda c: c.first_seen or 0)
        
        return clusters
    
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
            
            segment = MovementSegment(
                from_lat=c1.center_lat,
                from_lon=c1.center_lon,
                to_lat=c2.center_lat,
                to_lon=c2.center_lon,
                start_time=c1.last_seen or 0,
                end_time=c2.first_seen or 0,
                distance_meters=distance,
                speed_mps=speed
            )
            segments.append(segment)
            
            if distance >= self.MIN_MOVEMENT_DISTANCE:
                total_distance += distance
                speeds.append(speed)
        
        # Calculate area covered (bounding box)
        all_lats = [c.center_lat for c in clusters]
        all_lons = [c.center_lon for c in clusters]
        
        lat_range = max(all_lats) - min(all_lats)
        lon_range = max(all_lons) - min(all_lons)
        
        # Approximate area in square meters
        avg_lat = mean(all_lats)
        meters_per_degree_lat = 111320
        meters_per_degree_lon = 111320 * math.cos(math.radians(avg_lat))
        
        area_sq_m = (lat_range * meters_per_degree_lat) * (lon_range * meters_per_degree_lon)
        
        # Determine if stationary
        # Consider stationary if:
        # - Total distance is small
        # - Area covered is small
        # - Average speed is very low
        
        avg_speed = mean(speeds) if speeds else 0
        max_speed = max(speeds) if speeds else 0
        
        # Score movement indicators (0-100 for each)
        distance_score = min(100, total_distance / 10)  # 1000m = 100 score
        area_score = min(100, area_sq_m / 100)  # 10000 sq m = 100 score
        speed_score = min(100, avg_speed * 20)  # 5 m/s = 100 score
        
        movement_score = (distance_score + area_score + speed_score) / 3
        
        is_stationary = (
            total_distance < 100 and  # Less than 100m total movement
            area_sq_m < self.STATIONARY_MAX_AREA and  # Small area
            avg_speed < self.MIN_MOVEMENT_SPEED  # Very slow
        )
        
        # Calculate confidence based on how clear-cut the classification is
        if is_stationary:
            confidence = 100 - movement_score  # Higher score = less confident it's stationary
        else:
            confidence = movement_score  # Higher score = more confident it's moving
        
        # Clamp confidence
        confidence = max(30, min(95, confidence))
        
        # Store calculated values for later
        self._total_distance = total_distance
        self._area_sq_m = area_sq_m
        self._avg_speed = avg_speed
        self._max_speed = max_speed
        
        return is_stationary, confidence, segments
    
    def estimate_primary_location(self, clusters: List[LocationCluster]) -> Optional[Tuple[float, float]]:
        """Estimate the most likely device location.
        
        For stationary devices: the cluster with most sightings and best RSSI
        For moving devices: the most recent cluster
        """
        if not clusters:
            return None
        
        # Weight clusters by sighting count and RSSI
        best_cluster = max(
            clusters,
            key=lambda c: len(c.sightings) * (1 + (c.avg_rssi + 100) / 100 if c.avg_rssi else 1)
        )
        
        return (best_cluster.center_lat, best_cluster.center_lon)
    
    def generate_path_points(self) -> List[Dict[str, Any]]:
        """Generate path points for visualization on a map."""
        sightings_with_loc = [s for s in self.sightings if s.has_location]
        
        path_points = []
        for s in sightings_with_loc:
            path_points.append({
                'lat': s.lat,
                'lon': s.lon,
                'timestamp': s.timestamp,
                'timestamp_str': datetime.fromtimestamp(s.timestamp).isoformat(),
                'time_display': datetime.fromtimestamp(s.timestamp).strftime('%H:%M:%S'),
                'rssi': s.rssi,
                'source': s.source,
                'ssid': s.ssid,
                'name': s.name
            })
        
        return path_points
    
    def analyze(self) -> Optional[TriangulationResult]:
        """Run full triangulation and movement analysis.
        
        Returns:
            TriangulationResult or None if device not found
        """
        # Fetch data
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
        
        # Cluster locations
        clusters = self.cluster_locations(sightings)
        result.location_clusters = clusters
        
        # Analyze movement
        is_stationary, confidence, segments = self.analyze_movement(clusters)
        result.is_stationary = is_stationary
        result.movement_confidence = confidence
        result.movement_segments = segments
        
        # Add calculated statistics
        result.total_distance_meters = getattr(self, '_total_distance', 0)
        result.area_covered_sq_meters = getattr(self, '_area_sq_m', 0)
        result.avg_speed_mps = getattr(self, '_avg_speed', 0)
        result.max_speed_mps = getattr(self, '_max_speed', 0)
        
        # Estimate primary location
        result.estimated_location = self.estimate_primary_location(clusters)
        
        # Generate path points
        result.path_points = self.generate_path_points()
        
        self.result = result
        return result
    
    def print_summary(self):
        """Print a text summary to console."""
        if not self.result:
            print(f"No data found for device: {self.mac}")
            return
        
        r = self.result
        
        print("=" * 60)
        print("DEVICE TRIANGULATION ANALYSIS")
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
            for ssid in r.ssids[:5]:  # Show first 5
                print(f"    - {ssid}")
            if len(r.ssids) > 5:
                print(f"    ... and {len(r.ssids) - 5} more")
        
        print()
        
        # Observation summary
        print("OBSERVATION SUMMARY")
        print("-" * 40)
        print(f"  Total Sightings:       {r.total_sightings}")
        print(f"  With GPS Location:     {r.sightings_with_location}")
        
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
                if cluster.first_seen:
                    print(f"    First Seen: {datetime.fromtimestamp(cluster.first_seen).strftime('%H:%M:%S')}")
                if cluster.last_seen:
                    print(f"    Last Seen:  {datetime.fromtimestamp(cluster.last_seen).strftime('%H:%M:%S')}")
                print()
        
        # Estimated location
        if r.estimated_location:
            print("ESTIMATED PRIMARY LOCATION")
            print("-" * 40)
            print(f"  Latitude:  {r.estimated_location[0]:.6f}")
            print(f"  Longitude: {r.estimated_location[1]:.6f}")
            print(f"  https://www.google.com/maps?q={r.estimated_location[0]},{r.estimated_location[1]}")
        
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
