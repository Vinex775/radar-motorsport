import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import db
from app import _manual_event
from collectors.discovery import classify_access, detect_platform, detect_series, buscar_pistas_personalizadas, locale_for_query
from collectors.youtube import buscar_lives
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
        self.assertEqual(detect_series("British Hillclimb Championship live"), "Hillclimb / Subida de montanha")
        self.assertEqual(detect_series("NHRA drag racing live stream"), "Arrancada / Drag")
        self.assertEqual(detect_series("WorldSBK race"), "WorldSBK")
        self.assertEqual(classify_access("All rounds are LIVE and FREE on the official channel"), "free")
        self.assertEqual(classify_access("Free practice begins at 10:00"), "unknown")
        self.assertEqual(classify_access("Acesso pago por evento"), "ppv")

    def test_custom_news_search_parses_rss(self):
        rss = b'''<?xml version="1.0"?><rss><channel><item>
          <title>Swedish Karting Series C live stream free on YouTube</title>
          <link>https://example.com/kart-live</link>
          <description>Race live and free</description>
          <pubDate>Tue, 03 Nov 2026 08:00:00 GMT</pubDate>
          <source>Example Motorsport</source>
        </item></channel></rss>'''
        with patch("collectors.discovery._fetch_query", return_value=rss):
            results = buscar_pistas_personalizadas("Swedish karting series C")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["series"], "Karting")
        self.assertEqual(results[0]["access"], "free")
        self.assertIn("pista editorial", results[0]["note"])

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
            result = buscar_lives("Swedish karting")
        self.assertFalse(result["configured"])
        self.assertEqual(result["items"], [])


class CatalogTests(unittest.TestCase):
    def test_expanded_sources_and_presets(self):
        sources = load_watch_sources()
        presets = load_search_presets()
        self.assertGreaterEqual(len(sources), 20)
        self.assertGreaterEqual(len(presets), 20)
        self.assertIn("FIA Karting — Mundial / Europeu / Arrive & Drive", [s["series"] for s in sources])
        self.assertIn("Karting — Suécia / Escandinávia", [p["label"] for p in presets])
        self.assertTrue(all(s["access"] in {"free", "subscription", "ppv", "unknown"} for s in sources))


class EventTests(unittest.TestCase):
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
        self.assertIn("acesso", error)

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
