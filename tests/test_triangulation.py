import unittest

from triangulation import DeviceTriangulator, Sighting, LocationCluster


class TestTriangulationFixes(unittest.TestCase):
    def _make_sighting(self, ts, lat, lon, rssi=-60, source="bt"):
        return Sighting(
            timestamp=ts,
            lat=lat,
            lon=lon,
            rssi=rssi,
            source=source,
            scanner="scanner-1",
        )

    def test_filter_outliers_keeps_non_outlier_cloud(self):
        tri = DeviceTriangulator("AA:BB:CC:DD:EE:01")
        center_lat = 52.4064
        center_lon = 16.9252

        # Around ~1-3 meters jitter around center.
        sightings = [
            self._make_sighting(1000 + i, center_lat + (i - 10) * 0.000001, center_lon + (10 - i) * 0.000001)
            for i in range(20)
        ]

        flagged = tri.filter_outliers(sightings)

        self.assertEqual(flagged, 0)
        self.assertTrue(all(not s.is_outlier for s in sightings))

    def test_filter_outliers_flags_far_point(self):
        tri = DeviceTriangulator("AA:BB:CC:DD:EE:02")
        center_lat = 52.4064
        center_lon = 16.9252

        sightings = [
            self._make_sighting(2000 + i, center_lat + (i - 10) * 0.000001, center_lon + (10 - i) * 0.000001)
            for i in range(20)
        ]
        far = self._make_sighting(2101, center_lat + 0.005, center_lon + 0.005)
        sightings.append(far)

        flagged = tri.filter_outliers(sightings)

        self.assertGreaterEqual(flagged, 1)
        self.assertTrue(far.is_outlier)

    def test_analyze_movement_overlap_does_not_spike_speed(self):
        tri = DeviceTriangulator("AA:BB:CC:DD:EE:03")

        c1 = LocationCluster(
            center_lat=52.4064,
            center_lon=16.9252,
            sightings=[self._make_sighting(1000, 52.4064, 16.9252)],
            first_seen=1000,
            last_seen=1100,
        )
        c2 = LocationCluster(
            center_lat=52.4073,
            center_lon=16.9252,
            sightings=[self._make_sighting(1050, 52.4073, 16.9252)],
            first_seen=1050,
            last_seen=1200,
        )

        is_stationary, confidence, segments = tri.analyze_movement([c1, c2])

        # With overlapping windows, speed should be based on center-to-center
        # timing fallback (75s here), not an artificial 1-second divisor.
        expected_time_diff = 75
        expected_speed = segments[0].distance_meters / expected_time_diff

        self.assertEqual(len(segments), 1)
        self.assertAlmostEqual(segments[0].speed_mps, expected_speed, places=6)
        self.assertAlmostEqual(tri._avg_speed, expected_speed, places=6)
        self.assertAlmostEqual(tri._max_speed, expected_speed, places=6)
        self.assertLess(segments[0].speed_mps, segments[0].distance_meters)
        self.assertFalse(is_stationary)
        self.assertGreaterEqual(confidence, 30)

    def test_normal_non_outlier_movement_still_detected(self):
        tri = DeviceTriangulator("AA:BB:CC:DD:EE:04")

        # No outlier: all points tightly grouped.
        center_lat = 52.5000
        center_lon = 13.4000
        clean_sightings = [
            self._make_sighting(3000 + i, center_lat + i * 0.000001, center_lon - i * 0.000001)
            for i in range(10)
        ]
        flagged = tri.filter_outliers(clean_sightings)
        self.assertEqual(flagged, 0)

        # Normal movement with positive non-overlapping time gaps.
        c1 = LocationCluster(
            center_lat=52.5000,
            center_lon=13.4000,
            sightings=[self._make_sighting(4000, 52.5000, 13.4000)],
            first_seen=4000,
            last_seen=4010,
        )
        c2 = LocationCluster(
            center_lat=52.5010,
            center_lon=13.4000,
            sightings=[self._make_sighting(4110, 52.5010, 13.4000)],
            first_seen=4110,
            last_seen=4120,
        )
        c3 = LocationCluster(
            center_lat=52.5020,
            center_lon=13.4000,
            sightings=[self._make_sighting(4230, 52.5020, 13.4000)],
            first_seen=4230,
            last_seen=4240,
        )

        is_stationary, confidence, segments = tri.analyze_movement([c1, c2, c3])

        self.assertEqual(len(segments), 2)
        self.assertGreater(tri._total_distance, 100)
        self.assertGreater(tri._avg_speed, 0.3)
        self.assertFalse(is_stationary)
        self.assertGreaterEqual(confidence, 30)


if __name__ == "__main__":
    unittest.main()
