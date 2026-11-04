import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import db
from app import _manual_event
from collectors.discovery import classify_access, detect_platform, detect_series, search_custom_discovery_leads, locale_for_query, is_motorsport_result, is_reaction_or_commentary, is_stale_watch_guide, EXCLUDED_NEWS_TERMS
from collectors.youtube import search_live_videos, GLOBAL_LIVE_QUERY
from collectors import twitch, kick, live_now
from config import load_environment
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
        self.assertEqual(detect_platform("FlyingFinn.tv and YouTube broadcast"), "FlyingFinn.tv, YouTube")

    def test_broader_motorsport_detection(self):
        self.assertEqual(detect_series("Swedish club karting series C livestream"), "Karting")
        self.assertEqual(detect_series("British Hillclimb Championship live"), "Hillclimb")
        self.assertEqual(detect_series("NHRA drag racing live stream"), "Drag racing")
        self.assertEqual(detect_series("Autosuunnistus SM Riihimaki live broadcast"), "Autosuunnistus / precision navigation motorsport")
        self.assertEqual(detect_series("WorldSBK race"), "WorldSBK")
        self.assertEqual(classify_access("All rounds are LIVE and FREE on the official channel"), "free")
        self.assertEqual(classify_access("Free practice begins at 10:00"), "unknown")
        self.assertEqual(classify_access("Acesso pago por evento"), "ppv")

    def test_rejects_non_motorsport_racing(self):
        self.assertFalse(is_motorsport_result("Horse racing live from Ascot"))
        self.assertFalse(is_motorsport_result("Greyhound racing live"))
        self.assertTrue(is_motorsport_result("Autosuunnistus SM live stream"))
        self.assertTrue(is_motorsport_result("Live Formula Drift race"))
        self.assertTrue(is_motorsport_result("Folkrace live from Sweden"))
        self.assertTrue(is_motorsport_result("Local tractor pulling championship"))

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

    def test_old_watch_guides_are_historical_not_discarded(self):
        now = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
        old = "2026-11-01T12:00:00+00:00"
        fresh = "2026-11-03T11:00:00+00:00"
        self.assertTrue(is_stale_watch_guide(old, "GP Mexico 2026: where to watch live", now=now))
        self.assertFalse(is_stale_watch_guide(fresh, "GP Mexico 2026: where to watch live", now=now))
        self.assertFalse(is_stale_watch_guide(old, "Preview: next weekend's Swedish karting race", now=now))
        self.assertTrue(is_motorsport_result("GP Mexico 2026: where to watch live", "Formula 1 race"))

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
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["series"], "Karting")
        historical = next(item for item in results if item["id"] != results[0]["id"])
        self.assertEqual(historical["lead_status"], "historical_reference")
        self.assertFalse(historical["is_verified_live"])

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


    def test_custom_search_keeps_historical_broadcast_reference(self):
        rss = b'''<?xml version="1.0"?><rss><channel><item>
          <title>FlyingFinn.tv live: Autosuunnistus SM Riihimaki October 24</title>
          <link>https://example.com/flyingfinn</link>
          <description>Free live broadcast on Moottoriurheilu.tv YouTube channel. Autosuunnistus competition.</description>
          <pubDate>Wed, 21 Oct 2026 10:00:00 GMT</pubDate>
          <source>Autourheilu</source>
        </item></channel></rss>'''
        with patch("collectors.discovery._fetch_query", return_value=rss):
            results = search_custom_discovery_leads("Autosuunnistus SM Finland")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["lead_status"], "historical_reference")
        self.assertEqual(results[0]["platform"], "FlyingFinn.tv, Moottoriurheilu.tv, YouTube")
        self.assertEqual(results[0]["access"], "free")
        self.assertFalse(results[0]["is_verified_live"])

    def test_regional_news_locale(self):
        self.assertEqual(locale_for_query("karting live Brazil"), ("pt-BR", "BR", "BR:pt"))
        self.assertEqual(locale_for_query("Swedish karting series"), ("sv-SE", "SE", "SE:sv"))
        self.assertEqual(locale_for_query("Norwegian rally championship"), ("no-NO", "NO", "NO:no"))
        self.assertEqual(locale_for_query("Finnish speedway championship"), ("fi-FI", "FI", "FI:fi"))
        self.assertEqual(locale_for_query("karting Suécia"), ("sv-SE", "SE", "SE:sv"))
        self.assertEqual(locale_for_query("karting ao vivo Suécia"), ("sv-SE", "SE", "SE:sv"))
        self.assertEqual(locale_for_query("corrida ao vivo"), ("pt-BR", "BR", "BR:pt"))
        self.assertEqual(locale_for_query("French rally championship"), ("fr-FR", "FR", "FR:fr"))


    def test_youtube_live_scan_uses_broad_motorsport_query_and_filters_reacts(self):
        import io
        import json
        from urllib.parse import parse_qs, urlparse

        payload = {
            "items": [
                {"id": {"videoId": "race123"}, "snippet": {
                    "title": "Swedish Karting Series C — LIVE Race",
                    "description": "Official race broadcast from the circuit.",
                    "channelTitle": "Regional Karting TV",
                    "channelId": "channel1",
                    "publishedAt": "2026-11-03T10:00:00Z",
                    "liveBroadcastContent": "live",
                }},
                {"id": {"videoId": "react123"}, "snippet": {
                    "title": "React ao vivo: Swedish karting race",
                    "description": "Watch-along and second screen reaction.",
                    "channelTitle": "Reaction channel",
                    "liveBroadcastContent": "live",
                }},
            ]
        }
        response = io.BytesIO(json.dumps(payload).encode("utf-8"))
        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test-key"}), patch("collectors.youtube.urlopen", return_value=response) as mocked:
            result = search_live_videos("motorsport")
        self.assertTrue(result["configured"])
        self.assertEqual(len(result["items"]), 1)
        self.assertTrue(result["items"][0]["is_verified_live"])
        self.assertEqual(result["items"][0]["status"], "live_now")
        query = parse_qs(urlparse(mocked.call_args_list[0].args[0].full_url).query)["q"][0]
        self.assertIn("karting", query)
        self.assertIn("motocross", query)
        self.assertIn("speedway", query)
        self.assertIn("autosuunnistus", query)
        self.assertIn("automobilismo", query)
        self.assertIn("folkrace", query)
        self.assertIn("tractor pulling", query)
        self.assertIn("|", query)  # OR terms broaden the global scan across disciplines.
        self.assertLessEqual(len(query), 500)
        params = parse_qs(urlparse(mocked.call_args_list[0].args[0].full_url).query)
        self.assertEqual(params["eventType"], ["live"])
        self.assertEqual(params["maxResults"], ["50"])
        self.assertEqual(result["items"][0]["url"], "https://www.youtube.com/watch?v=race123")

    def test_youtube_api_optional_key(self):
        with patch.dict(os.environ, {}, clear=True):
            result = search_live_videos("Swedish karting")
        self.assertFalse(result["configured"])
        self.assertEqual(result["items"], [])


class MultiPlatformLiveTests(unittest.TestCase):
    def setUp(self):
        live_now._CACHE.clear()
        twitch._TOKEN = None
        twitch._TOKEN_EXPIRES = 0
        twitch._TOKEN_CLIENT_ID = None
        twitch._CATEGORY_CACHE.clear()
        kick._TOKEN = None
        kick._TOKEN_EXPIRES = 0
        kick._TOKEN_CREDENTIALS = None

    def test_twitch_and_kick_accept_short_motorsport_category_labels(self):
        self.assertTrue(twitch._motorsport_category("Rally"))
        self.assertTrue(twitch._motorsport_category("Folkrace"))
        self.assertTrue(kick._is_motorsport("Rally"))
        self.assertTrue(kick._is_motorsport("Autosuunnistus"))

    def test_twitch_connector_returns_active_racing_stream(self):
        payload = {"data": [{
            "id": "stream-1", "user_login": "localrace", "user_name": "Local Race TV",
            "game_name": "Motorsports", "title": "Regional karting championship — race 2",
            "viewer_count": 83, "started_at": "2026-11-03T14:00:00Z", "language": "en",
            "tags": ["Racing"],
            "thumbnail_url": "https://example.com/{width}x{height}.jpg",
        }], "pagination": {}}
        with patch.dict(os.environ, {"TWITCH_CLIENT_ID": "client", "TWITCH_CLIENT_SECRET": "secret"}), \
             patch("collectors.twitch._app_token", return_value="token"), \
             patch("collectors.twitch._find_categories", return_value=[{"id": "22", "name": "Motorsports"}]), \
             patch("collectors.twitch._api_get", return_value=payload):
            result = twitch.search_live_streams()
        self.assertTrue(result["configured"])
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["platform"], "Twitch")
        self.assertTrue(result["items"][0]["is_verified_live"])
        self.assertEqual(result["items"][0]["viewers"], 83)

    def test_kick_connector_returns_active_local_motorsport_stream(self):
        categories = {"data": [{"id": 42, "name": "Motorsports"}]}
        streams = {"data": [{
            "id": "kick-live-1", "title": "Autosuunnistus SM — live coverage",
            "category": {"id": 42, "name": "Motorsports"},
            "broadcaster_user": {"id": 5, "username": "finnishrace"},
            "channel": {"slug": "finnishrace"}, "viewer_count": 27,
            "started_at": "2026-11-03T13:10:00Z", "language_code": "fi",
            "tags": ["Motorsport"], "thumbnail": "https://example.com/live.jpg",
        }]}
        def fake_kick_api(path, params, token):
            return categories if path.endswith("/categories") else streams

        with patch.dict(os.environ, {"KICK_CLIENT_ID": "client", "KICK_CLIENT_SECRET": "secret"}), \
             patch("collectors.kick._app_token", return_value="token"), \
             patch("collectors.kick._api_get", side_effect=fake_kick_api):
            result = kick.search_live_streams()
        self.assertTrue(result["configured"])
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["platform"], "Kick")
        self.assertEqual(result["items"][0]["url"], "https://kick.com/finnishrace")

    def test_kick_connector_follows_cursor_and_prioritizes_newer_streams(self):
        categories = {"data": [{"id": 42, "name": "Motorsports"}]}
        oldest = {"data": [{
            "id": "old", "title": "Old Swedish karting race", "category": {"id": 42, "name": "Motorsports"},
            "broadcaster_user": {"id": 1, "username": "oldrace"}, "channel": {"slug": "oldrace"},
            "viewer_count": 4, "started_at": "2026-11-03T08:00:00Z", "language_code": "sv", "tags": [],
        }], "pagination": {"next_cursor": "next-page-cursor"}}
        newest = {"data": [{
            "id": "new", "title": "New Finnish autosuunnistus race", "category": {"id": 42, "name": "Motorsports"},
            "broadcaster_user": {"id": 2, "username": "newrace"}, "channel": {"slug": "newrace"},
            "viewer_count": 25, "started_at": "2026-11-03T14:00:00Z", "language_code": "fi", "tags": [],
        }], "pagination": {"next_cursor": ""}}
        def fake_kick_api(path, params, token):
            if path.endswith("/categories"):
                return categories
            if ("cursor", "next-page-cursor") in params:
                return newest
            return oldest

        with patch.dict(os.environ, {"KICK_CLIENT_ID": "client", "KICK_CLIENT_SECRET": "secret"}), \
             patch("collectors.kick._app_token", return_value="token"), \
             patch("collectors.kick._api_get", side_effect=fake_kick_api) as api:
            result = kick.search_live_streams()
        self.assertEqual([item["channel"] for item in result["items"]], ["newrace", "oldrace"])
        stream_calls = [call for call in api.call_args_list if call.args[0].endswith("/livestreams")]
        self.assertEqual(len(stream_calls), 2)
        self.assertIn(("cursor", "next-page-cursor"), stream_calls[-1].args[1])

    def test_unconfigured_platforms_do_not_fail_global_scan(self):
        with patch.dict(os.environ, {}, clear=True):
            result = live_now.search_all_live_streams("motorsport")
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["configured_sources"], 0)
        self.assertEqual(set(result["platforms"]), {"YouTube", "Twitch", "Kick"})

    def test_global_scan_merges_all_platforms_and_uses_cache(self):
        youtube_result = {"configured": True, "items": [{"url": "https://youtube.com/watch?v=1", "title": "Kart race", "viewers": 10}]}
        twitch_result = {"configured": True, "items": [{"url": "https://twitch.tv/race", "title": "Rally race", "viewers": 50}]}
        kick_result = {"configured": True, "items": [{"url": "https://kick.com/race", "title": "Club race", "viewers": 20}]}
        with patch("collectors.live_now.search_live_videos", return_value=youtube_result) as yt, \
             patch("collectors.live_now.search_twitch", return_value=twitch_result) as tw, \
             patch("collectors.live_now.search_kick", return_value=kick_result) as kk:
            first = live_now.search_all_live_streams("motorsport")
            second = live_now.search_all_live_streams("motorsport")
        self.assertEqual(first["count"], 3)
        self.assertEqual(first["items"][0]["platform"], "Twitch")
        self.assertTrue(second["platforms"]["YouTube"]["cached"])
        yt.assert_called_once(); tw.assert_called_once(); kk.assert_called_once()

    def test_dotenv_loads_credentials_without_overriding_existing_values(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text('YOUTUBE_API_KEY="from-file"\nTWITCH_CLIENT_ID=from-file-id\n', encoding="utf-8")
            with patch.dict(os.environ, {"YOUTUBE_API_KEY": "already-set"}, clear=True):
                load_environment(env_file)
                self.assertEqual(os.environ["YOUTUBE_API_KEY"], "already-set")
                self.assertEqual(os.environ["TWITCH_CLIENT_ID"], "from-file-id")


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
                self.assertEqual(removed, 2)
                saved = db.get_discoveries()
                self.assertEqual({item["id"] for item in saved}, {"stale", "kart"})
                stale = next(item for item in saved if item["id"] == "stale")
                self.assertEqual(stale["lead_status"], "historical_reference")
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


    def test_database_migrates_legacy_discoveries_table(self):
        with tempfile.TemporaryDirectory() as directory:
            old_path = db.DB_PATH
            db.DB_PATH = Path(directory) / "legacy.sqlite3"
            try:
                with db.connect() as conn:
                    conn.execute("CREATE TABLE discoveries (id TEXT PRIMARY KEY, title TEXT NOT NULL, summary TEXT, url TEXT NOT NULL UNIQUE, published_utc TEXT, source_name TEXT, series TEXT, platform TEXT, access TEXT, note TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
                db.init_db()
                with db.connect() as conn:
                    columns = {row[1] for row in conn.execute("PRAGMA table_info(discoveries)")}
                self.assertIn("lead_status", columns)
            finally:
                db.DB_PATH = old_path

    def test_database_connection_is_closed_after_context(self):
        with tempfile.TemporaryDirectory() as directory:
            old_path = db.DB_PATH
            db.DB_PATH = Path(directory) / "radar.sqlite3"
            try:
                with db.connect() as conn:
                    db.init_db()
                    connection = conn
                with self.assertRaises(Exception):
                    connection.execute("SELECT 1")
            finally:
                db.DB_PATH = old_path

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
