import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from collectors import live_now, youtube_upcoming


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        fixed = datetime(2026, 11, 5, 16, 15, tzinfo=ZoneInfo("America/Sao_Paulo"))
        return fixed.astimezone(tz) if tz else fixed


class SameDayBroadcastRetentionTests(unittest.TestCase):
    def setUp(self):
        live_now._CACHE.clear()

    def test_porsche_cup_remains_visible_after_its_published_start_time(self):
        now = datetime(2026, 11, 5, 19, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test-key"}), \
             patch("collectors.youtube_upcoming._request_json", side_effect=[{"items": []}, {"items": []}]), \
             patch("collectors.youtube_upcoming._video_details", return_value={}):
            result = youtube_upcoming.search_upcoming_videos("motorsport", now=now)

        porsche = next(item for item in result["items"] if item["id"] == "youtube:BFHxCOvY2Zw")
        self.assertEqual(porsche["status"], "start_time_passed")
        self.assertEqual(porsche["scheduled_start_at"], "2026-11-05T19:30:00+00:00")
        self.assertEqual(result["start_time_passed_count"], 1)
        self.assertEqual(result["future_events"], [])

    def test_same_day_archived_item_is_restored_even_when_api_returns_nothing(self):
        now = datetime(2026, 11, 5, 19, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        archived = {
            "date": "2026-11-05",
            "items": [{
                "id": "youtube:old-broadcast",
                "url": "https://www.youtube.com/watch?v=old-broadcast",
                "platform": "YouTube",
                "title": "Official karting race",
                "scheduled_start_at": "2026-11-05T18:00:00+00:00",
            }],
        }
        with patch("collectors.live_now.db.get_setting", return_value=json.dumps(archived)), \
             patch("collectors.live_now.db.set_setting"):
            restored = live_now._merge_today_archive([], [], now)

        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["status"], "start_time_passed")
        self.assertIn("has passed", restored[0]["note"])

    def test_live_and_future_today_streams_are_prioritized_before_passed_times(self):
        live_now._CACHE.clear()
        active = {"configured": True, "items": [{
            "id": "active", "url": "https://youtube.com/watch?v=active",
            "title": "GB3 Championship race LIVE", "platform": "YouTube", "status": "live_now",
        }]}
        scheduled = {"configured": True, "items": [
            {"id": "later", "url": "https://youtube.com/watch?v=later", "title": "Porsche Cup Carrera Cup", "platform": "YouTube", "scheduled_start_at": "2026-11-05T20:00:00+00:00", "status": "scheduled_today"},
            {"id": "passed", "url": "https://youtube.com/watch?v=passed", "title": "F4 Brasil Championship qualifying", "platform": "YouTube", "scheduled_start_at": "2026-11-05T18:00:00+00:00", "status": "start_time_passed"},
        ], "future_events": []}
        unavailable = {"configured": False, "items": []}

        with patch("collectors.live_now.datetime", FixedDateTime), \
             patch("collectors.live_now.search_live_videos", return_value=active), \
             patch("collectors.live_now.search_upcoming_videos", return_value=scheduled), \
             patch("collectors.live_now.search_twitch", return_value=unavailable), \
             patch("collectors.live_now.search_kick", return_value=unavailable), \
             patch("collectors.live_now.db.get_setting", return_value=None), \
             patch("collectors.live_now.db.set_setting"):
            result = live_now.search_all_live_streams("motorsport")

        self.assertEqual([item["id"] for item in result["items"]], ["active", "later", "passed"])
        self.assertEqual(result["active_count"], 1)
        self.assertEqual(result["scheduled_today_count"], 1)
        self.assertEqual(result["start_time_passed_count"], 1)

    def test_active_result_replaces_same_video_scheduled_record(self):
        now = datetime(2026, 11, 5, 19, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        scheduled = [{
            "id": "youtube:active-one", "url": "https://youtube.com/watch?v=active-one",
            "platform": "YouTube", "title": "WEC championship race",
            "scheduled_start_at": "2026-11-05T18:00:00+00:00",
        }]
        active = [{
            "id": "youtube:active-one", "url": "https://youtube.com/watch?v=active-one",
            "platform": "YouTube", "title": "WEC championship race", "status": "live_now",
        }]
        with patch("collectors.live_now.db.get_setting", return_value=None), \
             patch("collectors.live_now.db.set_setting"):
            restored = live_now._merge_today_archive(scheduled, active, now)
        self.assertEqual(restored, [])


if __name__ == "__main__":
    unittest.main()
