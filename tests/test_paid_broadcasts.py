from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from collectors import paid_broadcasts
import collectors.official_schedule  # make the submodule path patchable


class PaidBroadcastOptionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.watch_file = self.root / "watch_sources.json"
        self.monitored_file = self.root / "monitored_sources.json"
        self.watch_file.write_text(json.dumps([
            {
                "id": "f1-free", "series": "Formula 1", "region": "Brazil",
                "platform": "TV Globo / Globoplay", "access": "free",
                "url": "https://globoplay.globo.com/", "confidence": "official",
            },
            {
                "id": "f1-paid", "series": "Formula 1", "region": "Brazil",
                "platform": "SporTV / Globoplay", "access": "subscription",
                "url": "https://globoplay.globo.com/", "confidence": "official",
            },
            {
                "id": "wec-paid", "series": "FIA WEC / ELMS", "region": "Global",
                "platform": "FIAWEC+", "access": "subscription",
                "url": "https://plus.fiawec.com/", "confidence": "official",
            },
        ]), encoding="utf-8")
        self.monitored_file.write_text(json.dumps({"sources": [
            {
                "id": "dirtvision", "name": "DIRTVision", "confidence": "official_partner",
                "series": ["World of Outlaws"], "region": "United States",
                "watch_url": "https://www.dirtvision.com/",
            }
        ]}), encoding="utf-8")
        self.watch_patch = patch.object(paid_broadcasts, "WATCH_SOURCES_FILE", self.watch_file)
        self.monitored_patch = patch.object(paid_broadcasts, "MONITORED_SOURCES_FILE", self.monitored_file)
        self.watch_patch.start()
        self.monitored_patch.start()

    def tearDown(self) -> None:
        self.watch_patch.stop()
        self.monitored_patch.stop()
        self.temp.cleanup()

    def test_f1_resolves_free_and_subscription_options_for_same_platform_url(self) -> None:
        event = {"series": "Formula 1", "name": "Formula 1 — First Practice"}
        options = paid_broadcasts.resolve_watch_options(event)
        tiers = {(item["platform"], item["access"]) for item in options}
        self.assertIn(("TV Globo / Globoplay", "free"), tiers)
        self.assertIn(("SporTV / Globoplay", "subscription"), tiers)

    def test_wec_resolves_fiawec_plus_subscription(self) -> None:
        options = paid_broadcasts.resolve_watch_options({
            "series": "FIA World Endurance Championship", "name": "Qatar 1812km"
        })
        self.assertTrue(any(item["platform"] == "FIAWEC+" and item["access"] == "subscription" for item in options))

    def test_event_specific_paid_access_upgrades_unknown_partner_record(self) -> None:
        event = {
            "external_id": "wof-1", "series": "World of Outlaws / Super DIRTcar",
            "name": "World of Outlaws World Finals", "platform": "DIRTVision",
            "access": "subscription", "watch_url": "https://www.dirtvision.com/",
        }
        options = paid_broadcasts.resolve_watch_options(event)
        dirtvision = next(item for item in options if item["url"] == "https://www.dirtvision.com/")
        self.assertEqual(dirtvision["access"], "subscription")
        self.assertEqual(dirtvision["platform"], "DIRTVision")

    def test_today_collection_includes_today_and_excludes_tomorrow_without_claiming_live(self) -> None:
        fixed_now = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)  # 09:00 BRT
        registry = [
            {
                "external_id": "f1-today", "name": "Formula 1 — First Practice",
                "series": "Formula 1", "start": "2026-11-06T12:30:00-03:00",
                "end": "2026-11-06T13:30:00-03:00", "platform": "F1 TV / broadcasters",
                "access": "unknown", "watch_url": "https://www.formula1.com/en/racing/2026/brazil",
                "source_url": "https://www.formula1.com/en/racing/2026/brazil", "confidence": "official",
            },
            {
                "external_id": "f1-second-session", "name": "Formula 1 — Second Practice",
                "series": "Formula 1", "start": "2026-11-06T16:00:00-03:00",
                "end": "2026-11-06T17:00:00-03:00", "platform": "F1 TV / broadcasters",
                "access": "unknown", "watch_url": "https://www.formula1.com/en/racing/2026/brazil",
                "source_url": "https://www.formula1.com/en/racing/2026/brazil", "confidence": "official",
            },
            {
                "external_id": "wec-today", "name": "Qatar 1812km",
                "series": "FIA World Endurance Championship", "start": "2026-11-06T08:00:00Z",
                "end": "2026-11-06T16:00:00Z", "platform": "FIAWEC+",
                "access": "unknown", "watch_url": "https://plus.fiawec.com/",
                "source_url": "https://www.fiawec.com/", "confidence": "official",
            },
            {
                "external_id": "f1-tomorrow", "name": "Formula 1 — Qualifying",
                "series": "Formula 1", "start": "2026-11-07T15:00:00-03:00",
                "end": "2026-11-07T16:00:00-03:00", "platform": "F1 TV",
                "access": "unknown", "watch_url": "https://www.formula1.com/en/racing/2026/brazil",
                "source_url": "https://www.formula1.com/en/racing/2026/brazil", "confidence": "official",
            },
        ]
        with patch("collectors.official_schedule.fetch_official_schedule", return_value=registry), \
             patch("db.get_events", return_value=[]):
            items = paid_broadcasts.collect_today_paid_options(fixed_now)

        ids = {item["external_id"] for item in items}
        self.assertEqual(ids, {"f1-today", "f1-second-session", "wec-today"})
        f1_item = next(item for item in items if item["external_id"] == "f1-today")
        self.assertEqual(f1_item["status"], "scheduled_today")
        self.assertFalse(f1_item["is_verified_live"])
        self.assertTrue(any(option["access"] == "subscription" for option in f1_item["watch_options"]))
        wec_item = next(item for item in items if item["external_id"] == "wec-today")
        self.assertEqual(wec_item["status"], "schedule_window")
        self.assertFalse(wec_item["is_verified_live"])

    def test_schedule_enrichment_keeps_free_and_paid_access_choices(self) -> None:
        enriched = paid_broadcasts.enrich_event_with_watch_options({
            "external_id": "f1-future", "name": "Formula 1 — Grand Prix",
            "series": "Formula 1", "access": "unknown",
        })
        self.assertIn("watch_options", enriched)
        self.assertEqual({item["access"] for item in enriched["watch_options"]}, {"free", "subscription"})


if __name__ == "__main__":
    unittest.main()
