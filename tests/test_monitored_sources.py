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
        self.assertIn("nhra", by_id)
        self.assertIn("skusa", by_id)
        self.assertIn("rotax-karting", by_id)
        self.assertIn("asbk", by_id)
        self.assertIn("kart-chaser", by_id)
        self.assertGreaterEqual(len(sources), 24)
        self.assertTrue(all(source["confidence"] in monitored_sources.ALLOWED_CONFIDENCE for source in sources))

    def test_additions_registry_does_not_replace_main_registry(self):
        sources = monitored_sources.load_monitored_sources()
        by_id = {source["id"]: source for source in sources}
        self.assertIn("porsche-cup-brasil", by_id)
        self.assertIn("skusa", by_id)
        self.assertIn("rotax-karting", by_id)
        self.assertIn("asbk", by_id)

    def test_only_explicitly_enabled_trusted_youtube_channels_are_returned(self):
        channels = monitored_sources.get_youtube_sources()
        ids = {source["id"] for source in channels}
        self.assertIn("porsche-cup-brasil", ids)
        self.assertIn("yamaha-racing-brasil", ids)
        self.assertIn("fia-wec", ids)
        self.assertIn("skusa", ids)
        self.assertIn("rotax-karting", ids)
        self.assertIn("asbk", ids)
        self.assertIn("kart-chaser", ids)
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
            additions_path = Path(directory) / "additions.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            additions_path.write_text(json.dumps({"sources": []}), encoding="utf-8")
            with patch.object(monitored_sources, "MONITORED_SOURCES_FILE", path), patch.object(
                monitored_sources, "MONITORED_SOURCES_ADDITIONS_FILE", additions_path
            ):
                self.assertEqual(monitored_sources.get_youtube_sources(), [])

    def test_regional_broadcaster_needs_explicit_channel_opt_in(self):
        regional_source = {
            "id": "regional-broadcaster",
            "name": "Regional karting broadcaster",
            "confidence": "regional",
            "source_type": "regional_broadcast_partner",
            "official_url": "https://example.com",
            "channel_url": "https://www.youtube.com/@example",
            "youtube_channel": {"handle": "@example"},
            "monitoring": {"discovery": False, "youtube_upcoming": False},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"
            additions_path = Path(directory) / "additions.json"
            regional_source["monitoring"]["youtube_upcoming"] = False
            path.write_text(json.dumps({"sources": [regional_source]}), encoding="utf-8")
            additions_path.write_text(json.dumps({"sources": []}), encoding="utf-8")
            with patch.object(monitored_sources, "MONITORED_SOURCES_FILE", path), patch.object(
                monitored_sources, "MONITORED_SOURCES_ADDITIONS_FILE", additions_path
            ):
                self.assertEqual(monitored_sources.get_youtube_sources(), [])

            regional_source["monitoring"]["youtube_upcoming"] = True
            path.write_text(json.dumps({"sources": [regional_source]}), encoding="utf-8")
            with patch.object(monitored_sources, "MONITORED_SOURCES_FILE", path), patch.object(
                monitored_sources, "MONITORED_SOURCES_ADDITIONS_FILE", additions_path
            ):
                channels = monitored_sources.get_youtube_sources()
                self.assertEqual([source["id"] for source in channels], ["regional-broadcaster"])

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
            additions_path = Path(directory) / "additions.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            additions_path.write_text(json.dumps({"sources": []}), encoding="utf-8")
            with patch.object(monitored_sources, "MONITORED_SOURCES_FILE", path), patch.object(
                monitored_sources, "MONITORED_SOURCES_ADDITIONS_FILE", additions_path
            ):
                loaded = monitored_sources.load_monitored_sources()
        self.assertEqual([item["id"] for item in loaded], ["same"])


if __name__ == "__main__":
    unittest.main()
