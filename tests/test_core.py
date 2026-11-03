import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import db
from app import _manual_event
from collectors.discovery import classify_access, detect_platform, detect_series, search_custom_discovery_leads, locale_for_query, is_motorsport_result, is_reaction_or_commentary, is_stale_watch_guide, EXCLUDED_NEWS_TERMS
from collectors.youtube import search_live_videos
from radar import event_status, load_watch_sources, load_search_presets


class DiscoveryTests(unittest.TestCase):
    def test_access_classification(self):
        self.assertEqual(classify_access("Free live stream on YouTube"), "free")
        self.assertEqual(classify_access("Requires a monthly subscription"), "subscription")
        self.assertEqual(classify_access("Pay-per-view access available"), "ppv")
        self.assertEqual(classify_access("Live coverage details soon"), "unknown")

    def test_platform_and_series_detection(self):
        self.assertEqual(detect_platform("Watch the race on Twitch"), "Twitch")
        self.assertEqual(detect_series("Swedish junior karting livestream"), "Karting")
        self.assertEqual(detect_series("FIA World Endurance Championship WEC"), "FIA WEC")
        self.assertEqual(detect_series("WorldSBK race"), "WorldSBK")

    def test_broader_motorsport_detection(self):
        self.assertEqual(detect_series("Swedish club karting series C livestream"), "Karting")
        self.assertEqual(detect_series("British Hillclimb Championship live"), "Hillclimb")
        self.assertEqual(detect_series("NHRA drag racing live stream"), "Drag racing")
        self.assertEqual(detect_series("WorldSBK race"), "WorldSBK")
        self.assertEqual(classify_access("All rounds are LIVE and FREE on the official channel"), "free")
        self.assertEqual(classify_access("Free practice begins at 10:00"), "unknown")
        self.assertEqual(classify_access("Acesso pago por evento"), "ppv")

    def test_rejects_political_rallies(self):
        political_titles = [
            "WATCH LIVE: Senate candidate Ashley Hinson holds election rally in Des Moines",
            "WATCH LIVE: Abdul El-Sayed holds a rally in Detroit, Michigan",
            "Iowa GOP candidate holds rally as Election Day approaches",
            "Vance rallies GOP voters in New York, Ohio",
        ]
        for title in political_titles:
            with self.subTest(title=title):
                self.assertFalse(is_motorsport_result(title, "Live coverage and latest updates"))

    def test_keeps_real_rally_motorsport_results(self):
        valid_titles = [
            "WRC Rally Finland: watch the special stages live",
            "Swedish Rally Championship livestream with rally cars and co-drivers",
            "Rallycross championship race weekend live stream",
            "Karting Series C livestream from Sweden",
        ]
        for title in valid_titles:
            with self.subTest(title=title):
                self.assertTrue(is_motorsport_result(title))

    def test_rejects_reaction_streams_as_race_feed_leads(self):
        self.assertTrue(is_reaction_or_commentary("React ao vivo: Corrida do GP do Mexico", "Comments in real time"))
        self.assertTrue(is_reaction_or_commentary("F1 race watchalong live", "Second screen commentary"))
        self.assertFalse(is_reaction_or_commentary("Official live race feed: Swedish Karting Series C"))

    def test_filters_stale_watch_guides(self):
        now = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
        old = "2026-11-01T12:00:00+00:00"
        fresh = "2026-11-03T11:00:00+00:00"
        self.assertTrue(is_stale_watch_guide(old, "GP Mexico 2026: where to watch live" , now=now))
        self.assertFalse(is_stale_watch_guide(fresh, "GP Mexico 2026: where to watch live", now=now))
        self.assertFalse(is_stale_watch_guide(old, "Preview: next weekend's Swedish karting race", now=now))

    def test_query_excludes_political_noise(self):
        self.assertIn("-election", EXCLUDED_NEWS_TERMS)
        self.assertIn("-candidate", EXCLUDED_NEWS_TERMS)
        self.assertIn("-GOP", EXCLUDED_NEWS_TERMS)

    def test_custom_news_search_filters_political_rss_items(self):
        rss = b'''<?xml version="1.0"?><rss><channel>
          <item><title>WATCH LIVE: Senate candidate holds election rally</title>
            <link>https://example.com/political-rally</link>
            <description>Election day coverage</description>
            <pubDate>Tue, 03 Nov 2026 08:00:00 GMT</pubDate><source>Example News</source>
          </item>
          <item><title>React ao vivo: Corrida do GP do Mexico de Formula 1</title>
            <link>https://example.com/f1-react</link>
            <description>Comments in real time</description>
            <pubDate>Tue, 03 Nov 2026 08:00:00 GMT</pubDate><source>Example News</source>
          </item>
          <item><title>GP Mexico 2026 link assistir corrida ao vivo F1</title>
            <link>https://example.com/old-watch-guide</link>
            <description>Where to watch live</description>
            <pubDate>Sun, 01 Nov 2026 08:00:00 GMT</pubDate><source>Example News</source>
          </item>
          <item><title>Swedish Karting Series C live stream free on YouTube</title>
            <link>https://example.com/kart-live</link>
            <description>Race live and free</description>
            <pubDate>Tue, 03 Nov 2026 08:00:00 GMT</pubDate><source>Example Motorsport</source>
          </item>
        </channel></rss>'''
        with patch("collectors.discovery._fetch_query", return_value=rss):
            results = search_custom_discovery_leads("Swedish karting series C")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["series"], "Karting")

    def test_custom_news_search_parses_rss(self):
        rss = b'''<?xml version="1.0"?><rss><channel><item>
          <title>Swedish Karting Series C live stream free on YouTube</title>
          <link>https://example.com/kart-live</link>
          <description>Race live and free</description>
          <pubDate>Tue, 03 Nov 2026 08:00:00 GMT</pubDate>
          <source>Example Motorsport</source>
        </item></channel></rss>'''
        with patch("collectors.discovery._fetch_query", return_value=rss):
            results = search_custom_discovery_leads("Swedish karting series C")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["series"], "Karting")
        self.assertEqual(results[0]["access"], "free")
        self.assertIn("editorial lead", results[0]["note"])

    def test_regional_news_locale(self):
        self.assertEqual(locale_for_query("karting live Brazil"), ("pt-BR", "BR", "BR:pt"))
        self.assertEqual(locale_for_query("Swedish karting series"), ("sv-SE", "SE", "SE:sv"))
        self.assertEqual(locale_for_query("Norwegian rally championship"), ("no-NO", "NO", "NO:no"))
        self.assertEqual(locale_for_query("Finnish speedway championship"), ("fi-FI", "FI", "FI:fi"))
        self.assertEqual(locale_for_query("karting Suécia"), ("sv-SE", "SE", "SE:sv"))
        self.assertEqual(locale_for_query("karting ao vivo Suécia"), ("sv-SE", "SE", "SE:sv"))
        self.assertEqual(locale_for_query("corrida ao vivo"), ("pt-BR", "BR", "BR:pt"))
        self.assertEqual(locale_for_query("French rally championship"), ("fr-FR", "FR", "FR:fr"))

    def test_youtube_api_optional_key(self):
        with patch.dict(os.environ, {}, clear=True):
            result = search_live_videos("Swedish karting")
        self.assertFalse(result["configured"])
        self.assertEqual(result["items"], [])


class CatalogTests(unittest.TestCase):
    def test_expanded_sources_and_presets(self):
        sources = load_watch_sources()
        presets = load_search_presets()
        self.assertGreaterEqual(len(sources), 20)
        self.assertGreaterEqual(len(presets), 20)
        self.assertIn("FIA Karting — World / European / Arrive & Drive", [s["series"] for s in sources])
        self.assertIn("Karting — Sweden / Scandinavia", [p["label"] for p in presets])
        self.assertTrue(all(s["access"] in {"free", "subscription", "ppv", "unknown"} for s in sources))


class EventTests(unittest.TestCase):
    def test_database_purges_invalid_discovery_leads(self):
        with tempfile.TemporaryDirectory() as directory:
            old_path = db.DB_PATH
            db.DB_PATH = Path(directory) / "radar.sqlite3"
            try:
                db.init_db()
                db.save_discoveries([
                    {"id": "political", "title": "Senate candidate holds election rally", "url": "https://example.com/politics"},
                    {"id": "react", "title": "React ao vivo: Corrida do GP do Mexico de Formula 1", "summary": "Comments in real time", "url": "https://example.com/react", "published": "2026-11-03T08:00:00+00:00"},
                    {"id": "stale", "title": "GP Mexico 2026 link assistir corrida ao vivo F1", "summary": "Where to watch live", "url": "https://example.com/stale", "published": "2026-11-01T08:00:00+00:00"},
                    {"id": "kart", "title": "Swedish Karting Series C live stream", "url": "https://example.com/kart"},
                ])
                removed = db.purge_irrelevant_discoveries()
                self.assertEqual(removed, 3)
                self.assertEqual([item["id"] for item in db.get_discoveries()], ["kart"])
            finally:
                db.DB_PATH = old_path

    def test_event_status(self):
        now = datetime.now(timezone.utc)
        self.assertEqual(event_status({"start_utc": (now - timedelta(minutes=20)).isoformat(), "end_utc": (now + timedelta(minutes=40)).isoformat()}, now), "live")
        self.assertEqual(event_status({"start_utc": (now + timedelta(hours=2)).isoformat(), "end_utc": None}, now), "upcoming")
        self.assertEqual(event_status({"start_utc": None, "end_utc": None}, now), "unknown")
        self.assertEqual(event_status({"start_utc": (now - timedelta(minutes=20)).isoformat(), "end_utc": None}, now), "unknown")

    def test_manual_event_validation(self):
        valid = {
            "name": "Kart Cup",
            "series": "Karting",
            "start": "2026-11-04T15:00",
            "platform": "YouTube",
            "access": "unknown",
            "stream_url": "https://youtube.com/live/example",
        }
        event, error = _manual_event(valid)
        self.assertIsNone(error)
        self.assertEqual(event["series"], "Karting")
        invalid, error = _manual_event({**valid, "access": "maybe"})
        self.assertIsNone(invalid)
        self.assertIn("access", error)

    def test_database_upsert(self):
        with tempfile.TemporaryDirectory() as directory:
            old_path = db.DB_PATH
            db.DB_PATH = Path(directory) / "radar.sqlite3"
            try:
                db.init_db()
                db.save_manual_event({
                    "external_id": "manual:test", "name": "Test Race", "series": "Kart",
                    "start": "2026-11-04T18:00:00+00:00", "platform": "YouTube", "access": "free"
                })
                events = db.get_events()
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["name"], "Test Race")
            finally:
                db.DB_PATH = old_path


if __name__ == "__main__":
    unittest.main()
