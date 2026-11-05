import os
import unittest
from datetime import datetime
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo
from unittest.mock import patch

from collectors import youtube_upcoming, live_now


class YouTubeUpcomingBroadcastTests(unittest.TestCase):
    def setUp(self):
        live_now._CACHE.clear()

    def test_routes_today_to_live_now_and_later_dates_to_schedule(self):
        now = datetime(2026, 11, 5, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        search_payload = {
            "items": [
                {"id": {"videoId": "porsche-today"}, "snippet": {"title": "ET.9 Interlagos F1 Quali Sprint Challenge", "channelTitle": "Porsche Cup Brasil", "liveBroadcastContent": "upcoming"}},
                {"id": {"videoId": "gb3-tomorrow"}, "snippet": {"title": "GB3 Championship Race 2", "channelTitle": "GB3 Championship", "liveBroadcastContent": "upcoming"}},
                {"id": {"videoId": "old-race"}, "snippet": {"title": "WEC race live", "channelTitle": "WEC", "liveBroadcastContent": "upcoming"}},
            ]
        }
        channel_payload = {"items": [search_payload["items"][0]]}
        details = {
            "porsche-today": {
                "id": "porsche-today",
                "snippet": {"title": "ET.9 Interlagos F1 Quali Sprint Challenge", "channelTitle": "Porsche Cup Brasil", "liveBroadcastContent": "upcoming", "description": "Official Porsche Cup Brazil broadcast"},
                "liveStreamingDetails": {"scheduledStartTime": "2026-11-05T16:30:00-03:00"},
            },
            "gb3-tomorrow": {
                "id": "gb3-tomorrow",
                "snippet": {"title": "GB3 Championship Race 2", "channelTitle": "GB3 Championship", "liveBroadcastContent": "upcoming", "description": "Official GB3 race broadcast"},
                "liveStreamingDetails": {"scheduledStartTime": "2026-11-06T11:00:00-03:00"},
            },
            "old-race": {
                "id": "old-race",
                "snippet": {"title": "WEC race live", "channelTitle": "WEC", "liveBroadcastContent": "upcoming", "description": "Race"},
                "liveStreamingDetails": {"scheduledStartTime": "2026-11-04T10:00:00-03:00"},
            },
        }
        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test-key"}), \
             patch("collectors.youtube_upcoming._request_json", side_effect=[
                 channel_payload, search_payload
             ]) as request, \
             patch("collectors.youtube_upcoming._video_details", return_value=details):
            result = youtube_upcoming.search_upcoming_videos("motorsport", now=now)

        self.assertEqual([item["id"] for item in result["items"]], ["youtube:porsche-today"])
        self.assertEqual(result["items"][0]["status"], "scheduled_today")
        self.assertEqual(result["items"][0]["scheduled_start_at"], "2026-11-05T19:30:00+00:00")
        self.assertEqual([event["external_id"] for event in result["future_events"]], ["youtube:gb3-tomorrow"])
        self.assertEqual(result["future_events"][0]["start_utc"], "2026-11-06T14:00:00+00:00")
        self.assertEqual(request.call_count, 2)
        channel_params = parse_qs(urlparse(request.call_args_list[0].args[0]).query)
        global_params = parse_qs(urlparse(request.call_args_list[1].args[0]).query)
        self.assertEqual(channel_params["eventType"], ["upcoming"])
        self.assertEqual(channel_params["channelId"], ["UCwiRFcstDPKaCiOTXuoFhrQ"])
        self.assertNotIn("q", channel_params)
        self.assertIn("Porsche Cup", global_params["q"][0])
        self.assertIn("Formula 1", global_params["q"][0])

    def test_finds_porsche_stream_from_official_channel_when_global_search_misses_it(self):
        now = datetime(2026, 11, 5, 13, 23, tzinfo=ZoneInfo("America/Sao_Paulo"))
        channel_payload = {
            "items": [{
                "id": {"videoId": "BFHxCOvY2Zw"},
                "snippet": {
                    "title": "ET.9 | INTERLAGOS (F1) | QUALI - SPRINT CHALLENGE | TEMPORADA 2026",
                    "channelTitle": "Porsche Cup Brasil",
                    "liveBroadcastContent": "upcoming",
                },
            }]
        }
        details = {
            "BFHxCOvY2Zw": {
                "id": "BFHxCOvY2Zw",
                "snippet": {
                    "title": "ET.9 | INTERLAGOS (F1) | QUALI - SPRINT CHALLENGE | TEMPORADA 2026",
                    "channelTitle": "Porsche Cup Brasil",
                    "liveBroadcastContent": "upcoming",
                    "description": "Transmissão oficial Porsche Cup Brasil. Classificatório Sprint Challenge em Interlagos.",
                },
                "liveStreamingDetails": {
                    "scheduledStartTime": "2026-11-05T16:30:00-03:00"
                },
            }
        }
        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test-key"}), \
             patch("collectors.youtube_upcoming._request_json", side_effect=[
                 channel_payload, {"items": []}
             ]) as request, \
             patch("collectors.youtube_upcoming._video_details", return_value=details):
            result = youtube_upcoming.search_upcoming_videos("motorsport", now=now)

        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["id"], "youtube:BFHxCOvY2Zw")
        self.assertEqual(result["items"][0]["status"], "scheduled_today")
        self.assertEqual(result["items"][0]["scheduled_start_at"], "2026-11-05T19:30:00+00:00")
        self.assertEqual(result["items"][0]["url"], "https://www.youtube.com/watch?v=BFHxCOvY2Zw")
        self.assertEqual(result["future_events"], [])
        channel_params = parse_qs(urlparse(request.call_args_list[0].args[0]).query)
        self.assertEqual(channel_params["channelId"], ["UCwiRFcstDPKaCiOTXuoFhrQ"])

    def test_rejects_video_game_scheduled_streams(self):
        now = datetime(2026, 11, 5, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        search_payload = {"items": [{"id": {"videoId": "game"}, "snippet": {"title": "PS1 Racing Games!", "channelTitle": "Retro games", "liveBroadcastContent": "upcoming"}}]}
        details = {"game": {"id": "game", "snippet": {"title": "PS1 Racing Games!", "channelTitle": "Retro games", "liveBroadcastContent": "upcoming", "description": "Classic games"}, "liveStreamingDetails": {"scheduledStartTime": "2026-11-05T16:30:00-03:00"}}}
        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test-key"}), \
             patch("collectors.youtube_upcoming._request_json", side_effect=[search_payload, search_payload]), \
             patch("collectors.youtube_upcoming._video_details", return_value=details):
            result = youtube_upcoming.search_upcoming_videos("motorsport", now=now)
        self.assertEqual(result["items"], [])

    def test_unconfigured_youtube_returns_empty_lists(self):
        with patch.dict(os.environ, {}, clear=True):
            result = youtube_upcoming.search_upcoming_videos()
        self.assertFalse(result["configured"])
        self.assertEqual(result["items"], [])
        self.assertEqual(result["future_events"], [])


class LiveNowTodayMergeTests(unittest.TestCase):
    def setUp(self):
        live_now._CACHE.clear()

    def test_global_scan_merges_active_and_today_streams_and_returns_future_events(self):
        active = {"configured": True, "items": [{"id": "active-1", "url": "https://youtube.com/watch?v=active", "title": "WEC 8 Hours race", "platform": "YouTube"}]}
        today = {"configured": True, "items": [{"id": "scheduled-1", "url": "https://youtube.com/watch?v=today", "title": "F1 practice", "status": "scheduled_today", "scheduled_start_at": "2026-11-05T19:30:00+00:00"}], "future_events": [{"external_id": "youtube:tomorrow", "name": "GB3 Race 2", "series": "GB3", "start_utc": "2026-11-06T14:00:00+00:00"}]}
        twitch = {"configured": False, "items": []}
        kick = {"configured": False, "items": []}
        with patch("collectors.live_now.search_live_videos", return_value=active), \
             patch("collectors.live_now.search_upcoming_videos", return_value=today), \
             patch("collectors.live_now.search_twitch", return_value=twitch), \
             patch("collectors.live_now.search_kick", return_value=kick):
            result = live_now.search_all_live_streams("motorsport")
        self.assertEqual(result["active_count"], 1)
        self.assertEqual(result["scheduled_today_count"], 1)
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["future_events"]), 1)
        self.assertEqual(result["future_events"][0]["external_id"], "youtube:tomorrow")
        self.assertEqual(result["refresh_policy"]["youtube_scheduled_minutes"], 120)


if __name__ == "__main__":
    unittest.main()
