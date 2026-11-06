import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collectors import monitored_sources


class MonitoredSourcesTests(unittest.TestCase):
    def test_registry_keeps_season_independent_official_sources(self):
        sources = monitored_sources.load_monitored_sources()
        by_id = {source["id"]: source for source in sources}
        self.assertIn("porsche-cup-brasil", by_id)
        self.assertIn("yamaha-racing-brasil", by_id)
        self.assertIn("world-of-outlaws", by_id)
        self.assertIn("powri", by_id)
        self.assertGreaterEqual(len(sources), 20)
        self.assertTrue(all(source["confidence"] in monitored_sources.ALLOWED_CONFIDENCE for source in sources))

    def test_only_explicitly_enabled_youtube_channels_are_returned(self):
        channels = monitored_sources.get_youtube_sources()
        ids = {source["id"] for source in channels}
        self.assertIn("porsche-cup-brasil", ids)
        self.assertIn("yamaha-racing-brasil", ids)
        self.assertIn("fia-wec", ids)
        self.assertNotIn("s2ftv", ids)
        self.assertTrue(all(source["youtube_channel"] for source in channels))

    def test_official_broadcast_partners_are_not_scanned_as_championship_channels(self):
        payload = {
            "schema_version": 1,
            "sources": [{
                "id": "partner-channel",
                "name": "Official streaming partner",
                "confidence": "official_partner",
                "official_url": "https://example.com",
                "youtube_channel": {"channel_id": "UCpartner123"},
                "monitoring": {"discovery": True, "youtube_upcoming": True},
            }]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(monitored_sources, "MONITORED_SOURCES_FILE", path):
                self.assertEqual(monitored_sources.get_youtube_sources(), [])

    def test_registry_rejects_untrusted_and_duplicate_rows(self):
        payload = {
            "schema_version": 1,
            "sources": [
                {"id": "same", "name": "Official A", "confidence": "official", "official_url": "https://example.com", "monitoring": {"discovery": True}},
                {"id": "same", "name": "Duplicate", "confidence": "official", "official_url": "https://example.org", "monitoring": {"discovery": True}},
                {"id": "untrusted", "name": "Unverified", "confidence": "community", "official_url": "https://example.net", "monitoring": {"discovery": True}}
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(monitored_sources, "MONITORED_SOURCES_FILE", path):
                loaded = monitored_sources.load_monitored_sources()
        self.assertEqual([item["id"] for item in loaded], ["same"])


if __name__ == "__main__":
    unittest.main()
