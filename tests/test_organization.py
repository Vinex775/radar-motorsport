import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import radar
from collectors.discovery import is_upcoming_discovery, _parse_feed
from collectors.calendario_dtm import _is_future_or_active


class DiscoveryClassificationTests(unittest.TestCase):
    def test_future_calendar_is_a_discovery_lead(self):
        now = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
        self.assertTrue(is_upcoming_discovery(
            "DTM 2027 calendar announced with eight race weekends",
            "The next season visits Red Bull Ring and Oschersleben.",
            "Wed, 04 Nov 2026 10:00:00 GMT",
            now=now,
        ))

    def test_recent_this_weekend_preview_is_upcoming(self):
        now = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
        self.assertTrue(is_upcoming_discovery(
            "World of Outlaws preview: racing this weekend",
            "Upcoming dirt track racing at the Charlotte World Finals.",
            "Thu, 05 Nov 2026 08:00:00 GMT",
            now=now,
        ))

    def test_uol_post_session_react_is_not_future(self):
        now = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
        self.assertFalse(is_upcoming_discovery(
            "F1 AO VIVO: Acompanhe a corrida sprint do GP da Holanda e o programa Pódio Sprint",
            "Melhores comentários da corrida sprint no react e no programa pós-sessão.",
            "Sat, 22 Aug 2026 16:00:00 GMT",
            now=now,
        ))


    def test_feed_separates_future_calendar_from_old_watch_page(self):
        rss = b"""<?xml version='1.0'?><rss><channel>
          <item>
            <title>DTM 2027 calendar announced with eight race weekends</title>
            <link>https://example.com/dtm-2027</link>
            <description>Upcoming season begins in April 2027.</description>
            <pubDate>Wed, 04 Nov 2026 10:00:00 GMT</pubDate>
            <source>Official Motorsport</source>
          </item>
          <item>
            <title>F1 AO VIVO: Dutch GP Sprint watch guide</title>
            <link>https://example.com/old-f1-live</link>
            <description>Where to watch the race live.</description>
            <pubDate>Sat, 22 Aug 2026 16:00:00 GMT</pubDate>
            <source>Old News</source>
          </item>
        </channel></rss>"""
        results = _parse_feed(rss)
        self.assertEqual(len(results), 2)
        future = next(item for item in results if "2027" in item["title"])
        old = next(item for item in results if "Dutch GP" in item["title"])
        self.assertEqual(future["lead_status"], "upcoming_lead")
        self.assertEqual(old["lead_status"], "historical_reference")

    def test_old_live_guide_is_not_future(self):
        now = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
        self.assertFalse(is_upcoming_discovery(
            "Porsche Cup Brasil: AO VIVO corrida 1 de Le Mans",
            "Watch the race live.",
            "Sat, 13 Jun 2026 10:00:00 GMT",
            now=now,
        ))


class ScheduleClassificationTests(unittest.TestCase):
    def test_dtm_weekend_range_must_be_future_or_active(self):
        now = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
        future = now + timedelta(days=160)
        ended = now - timedelta(days=10)
        self.assertTrue(_is_future_or_active(future, future + timedelta(days=3), now))
        self.assertTrue(_is_future_or_active(ended, now + timedelta(hours=1), now))
        self.assertFalse(_is_future_or_active(ended, ended + timedelta(days=2), now))
        self.assertFalse(_is_future_or_active(ended, None, now))

    def test_schedule_dashboard_exposes_only_future_events(self):
        now = datetime.now(timezone.utc)
        events = [
            {"id": 1, "name": "Future race", "start_utc": (now + timedelta(days=10)).isoformat(), "end_utc": (now + timedelta(days=12)).isoformat()},
            {"id": 2, "name": "Past race", "start_utc": (now - timedelta(days=10)).isoformat(), "end_utc": (now - timedelta(days=8)).isoformat()},
            {"id": 3, "name": "In-progress session", "start_utc": (now - timedelta(hours=1)).isoformat(), "end_utc": (now + timedelta(hours=1)).isoformat()},
        ]
        with patch("radar.db.get_events", return_value=events), \
             patch("radar.db.purge_irrelevant_discoveries"), \
             patch("radar.db.get_discoveries", return_value=[]), \
             patch("radar.db.get_setting", return_value=None), \
             patch("radar.load_watch_sources", return_value=[]), \
             patch("radar.load_search_presets", return_value=[]):
            dashboard = radar.dashboard_data()
        self.assertEqual([event["name"] for event in dashboard["events"]], ["Future race"])
        self.assertEqual(dashboard["stats"]["upcoming"], 1)


class OfficialWatchDirectoryTests(unittest.TestCase):
    def test_where_to_watch_excludes_community_sources_and_adds_official_pages(self):
        sample = [
            {"id": "official", "confidence": "official", "url": "https://example.com/official"},
            {"id": "regional", "confidence": "regional", "url": "https://example.com/regional"},
            {"id": "community", "confidence": "community-official", "url": "https://example.com/community"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            source_file = Path(directory) / "watch_sources.json"
            source_file.write_text(json.dumps(sample), encoding="utf-8")
            with patch.object(radar, "WATCH_SOURCES_FILE", source_file):
                sources = radar.load_watch_sources()
        ids = {source["id"] for source in sources}
        self.assertIn("official", ids)
        self.assertIn("regional", ids)
        self.assertNotIn("community", ids)
        self.assertIn("dirtvision-world-of-outlaws", ids)
        self.assertIn("imsa-domestic-coverage", ids)
        self.assertIn("karting-sm-finland", ids)
        self.assertTrue(all(source["confidence"] in {"official", "regional"} for source in sources))


if __name__ == "__main__":
    unittest.main()
