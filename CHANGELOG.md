# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Changed
- Unified database path resolution across scanner core, Web UI, and confidence analyzer to avoid divergent behavior when optional storage paths are unavailable.
- Added writable fallback selection for database location (env override, configured SD path, existing test DBs, and runtime fallbacks).
- Hardened supervisor backup behavior to skip backup cycles when removable mount targets are not mounted.

### Added
- Regression tests for database path resolution precedence and fallback behavior.

### Operational impact
- Scanner and Web UI continue to run when pendrive is absent.
- Pendrive remains optional and backup-only; primary database operation no longer depends on it.

### Reference
- Commit: 636c916

## [2026-07-18]

### Changed
- Improved BLE manufacturer identification determinism in scanner pipeline.
- Strengthened WiFi device-type classification to reduce false router matches for phone hotspots.
- Added WiFi packet-role dominance logic (Beacon vs ProbeRequest) for more robust AP/client inference.

### Technical details
- Scanner now chooses manufacturer data deterministically (prefer known BT SIG company IDs, then lowest ID).
- Classifier now applies hotspot safeguards in beacon fallback and better distinguishes router vs phone heuristics.
- Confidence analyzer now classifies mixed WiFi packet-role data using dominance thresholds instead of only pure Beacon/ProbeRequest cases.

### Reference
- Commit: 1fd531c
