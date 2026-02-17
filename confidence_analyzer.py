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
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

# Import settings for database path
from settings import SD_STORAGE, DB_FILE

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


class ConfidenceAnalyzer:
    """Analyzes device patterns and calculates confidence scores."""
    
    # Thresholds for analysis
    BOUNDARY_PERCENT = 0.10  # First/last 10% of session
    STRONG_RSSI_THRESHOLD = -60  # dBm, signals stronger than this are "strong"
    HIGH_PRESENCE_RATIO = 0.80  # Device present for >80% of session
    MEDIUM_PRESENCE_RATIO = 0.50  # Device present for >50% of session
    HIGH_SIGHTING_RATE = 0.70  # Sighting rate relative to expected
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self.session_stats: Optional[SessionStats] = None
        self.analyses: List[DeviceAnalysis] = []
        
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
        con = self.connect()
        try:
            # Get device info
            device = con.execute(
                "SELECT first_seen, last_seen, confidence FROM devices WHERE addr = ?",
                (addr,)
            ).fetchone()
            
            if not device:
                return None
            
            first_seen, last_seen, old_confidence = device
            
            # Get all sightings for this device
            sightings = con.execute("""
                SELECT ts_unix, rssi FROM sightings 
                WHERE addr = ? AND ts_unix IS NOT NULL
                ORDER BY ts_unix
            """, (addr,)).fetchall()
            
            sighting_count = len(sightings)
            
            # Calculate average RSSI
            rssi_values = [s[1] for s in sightings if s[1] is not None]
            avg_rssi = sum(rssi_values) / len(rssi_values) if rssi_values else None
            
            # Calculate presence ratio (capped at 1.0)
            device_duration = last_seen - first_seen
            presence_ratio = min(1.0, device_duration / session.duration) if session.duration > 0 else 0
            
            # Analyze session boundaries
            boundary_window = session.duration * self.BOUNDARY_PERCENT
            early_cutoff = session.start_time + boundary_window
            late_cutoff = session.end_time - boundary_window
            
            early_sightings = [(ts, rssi) for ts, rssi in sightings if ts <= early_cutoff]
            late_sightings = [(ts, rssi) for ts, rssi in sightings if ts >= late_cutoff]
            
            early_presence = len(early_sightings) > 0
            late_presence = len(late_sightings) > 0
            
            early_rssi_vals = [r for _, r in early_sightings if r is not None]
            late_rssi_vals = [r for _, r in late_sightings if r is not None]
            
            early_rssi = sum(early_rssi_vals) / len(early_rssi_vals) if early_rssi_vals else None
            late_rssi = sum(late_rssi_vals) / len(late_rssi_vals) if late_rssi_vals else None
            
            # Calculate new confidence
            new_confidence, factors = self._calculate_confidence(
                presence_ratio=presence_ratio,
                sighting_count=sighting_count,
                session_duration=session.duration,
                early_presence=early_presence,
                late_presence=late_presence,
                early_rssi=early_rssi,
                late_rssi=late_rssi,
                avg_rssi=avg_rssi
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
                factors=factors
            )
        finally:
            con.close()
    
    def analyze_wifi_device(self, mac: str, session: SessionStats) -> DeviceAnalysis:
        """Analyze a single WiFi device."""
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
            
            # Get all associations for this device
            associations = con.execute("""
                SELECT ts_unix, rssi FROM wifi_associations 
                WHERE mac = ? AND ts_unix IS NOT NULL
                ORDER BY ts_unix
            """, (mac,)).fetchall()
            
            sighting_count = len(associations)
            
            # Calculate average RSSI
            rssi_values = [a[1] for a in associations if a[1] is not None]
            avg_rssi = sum(rssi_values) / len(rssi_values) if rssi_values else None
            
            # Calculate presence ratio (capped at 1.0)
            device_duration = last_seen - first_seen
            presence_ratio = min(1.0, device_duration / session.duration) if session.duration > 0 else 0
            
            # Analyze session boundaries
            boundary_window = session.duration * self.BOUNDARY_PERCENT
            early_cutoff = session.start_time + boundary_window
            late_cutoff = session.end_time - boundary_window
            
            early_associations = [(ts, rssi) for ts, rssi in associations if ts <= early_cutoff]
            late_associations = [(ts, rssi) for ts, rssi in associations if ts >= late_cutoff]
            
            early_presence = len(early_associations) > 0
            late_presence = len(late_associations) > 0
            
            early_rssi_vals = [r for _, r in early_associations if r is not None]
            late_rssi_vals = [r for _, r in late_associations if r is not None]
            
            early_rssi = sum(early_rssi_vals) / len(early_rssi_vals) if early_rssi_vals else None
            late_rssi = sum(late_rssi_vals) / len(late_rssi_vals) if late_rssi_vals else None
            
            # Calculate new confidence
            new_confidence, factors = self._calculate_confidence(
                presence_ratio=presence_ratio,
                sighting_count=sighting_count,
                session_duration=session.duration,
                early_presence=early_presence,
                late_presence=late_presence,
                early_rssi=early_rssi,
                late_rssi=late_rssi,
                avg_rssi=avg_rssi
            )
            
            return DeviceAnalysis(
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
                factors=factors
            )
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
        avg_rssi: Optional[float]
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
    
    def apply_updates(self) -> Dict[str, int]:
        """Apply confidence updates to the database."""
        if not self.analyses:
            return {"bt_updated": 0, "wifi_updated": 0}
        
        con = self.connect()
        bt_count = 0
        wifi_count = 0
        
        try:
            for analysis in self.analyses:
                if analysis.device_type == "bt":
                    con.execute(
                        "UPDATE devices SET confidence = ? WHERE addr = ?",
                        (analysis.new_confidence, analysis.mac)
                    )
                    bt_count += 1
                else:
                    con.execute(
                        "UPDATE wifi_devices SET confidence = ? WHERE mac = ?",
                        (analysis.new_confidence, analysis.mac)
                    )
                    wifi_count += 1
            
            con.commit()
        finally:
            con.close()
        
        return {"bt_updated": bt_count, "wifi_updated": wifi_count}
    
    def get_summary(self) -> Dict:
        """Get analysis summary for reporting."""
        if not self.session_stats or not self.analyses:
            return {}
        
        bt_analyses = [a for a in self.analyses if a.device_type == "bt"]
        wifi_analyses = [a for a in self.analyses if a.device_type == "wifi"]
        
        high_confidence = [a for a in self.analyses if a.new_confidence >= 70]
        low_confidence = [a for a in self.analyses if a.new_confidence <= 30]
        
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
                "low_confidence": len(low_confidence)
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
            print(f"  Presence ratio: {analysis.presence_ratio:.1%}")
            print(f"  Boundaries: early={analysis.early_presence}, late={analysis.late_presence}")
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
        print("Done!")
        summary["updates"] = result
    else:
        print(f"\n[DRY RUN] No changes applied to database.")
        summary["updates"] = {"bt_updated": 0, "wifi_updated": 0, "dry_run": True}
    
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
