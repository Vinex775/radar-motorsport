import json
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from collectors import live_now
from app import _browser_timezone
import radar


LOCAL_MINUS_3 = timezone(timedelta(hours=-3))


class BrowserLocalDayRoutingTests(unittest.TestCase):
    def setUp(self):
        live_now._CACHE.clear()

    def test_browser_timezone_parser_uses_iana_name_or_offset_fallback(self):
        iana = _browser_timezone("/api/live-now?time_zone=America%2FSao_Paulo&utc_offset_minutes=180")
        fallback = _browser_timezone("/api/live-now?time_zone=Not%2FAZone&utc_offset_minutes=180")
        instant = datetime(2026, 11, 6, 1, 30, tzinfo=timezone.utc)
        self.assertEqual(instant.astimezone(iana).date().isoformat(), "2026-11-05")
        self.assertEqual(instant.astimezone(fallback).date().isoformat(), "2026-11-05")

    def test_live_scan_passes_browser_local_clock_to_youtube_upcoming(self):
        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                instant = datetime(2026, 11, 6, 1, 30, tzinfo=timezone.utc)
                return instant.astimezone(tz) if tz else instant

        unavailable = {"configured": False, "items": []}
        scheduled = {"configured": True, "items": [], "future_events": []}
        with patch("collectors.live_now.datetime", FixedDateTime), \
             patch("collectors.live_now.search_live_videos", return_value=unavailable), \
             patch("collectors.live_now.search_upcoming_videos", return_value=scheduled) as upcoming, \
             patch("collectors.live_now.search_twitch", return_value=unavailable), \
             patch("collectors.live_now.search_kick", return_value=unavailable), \
             patch("collectors.live_now.db.get_setting", return_value=None), \
             patch("collectors.live_now.db.set_setting"), \
             patch("collectors.live_now.db.get_events", return_value=[]):
            result = live_now.search_all_live_streams("motorsport", local_tz=LOCAL_MINUS_3)

        passed_now = upcoming.call_args.kwargs["now"]
        self.assertEqual(passed_now.date().isoformat(), "2026-11-05")
        self.assertEqual(passed_now.hour, 22)
        self.assertEqual(passed_now.utcoffset(), timedelta(hours=-3))
        self.assertEqual(result["local_date"], "2026-11-05")
        self.assertEqual(result["local_utc_offset_minutes"], -180)

    def test_saved_tomorrow_utc_broadcast_is_recovered_when_it_is_today_in_browser_timezone(self):
        local_now = datetime(2026, 11, 5, 22, 30, tzinfo=LOCAL_MINUS_3)
        utc_times = ["01:40", "01:45", "01:50", "01:55", "02:00", "02:05", "02:10"]
        saved_events = [
            {
                "source": "youtube_scheduled",
                "external_id": f"youtube:night-race-{index}",
                "name": f"Official GB3 Championship Race {index}",
                "series": "GB3 Championship",
                "category": "Scheduled broadcast",
                "kind": "YouTube broadcast",
                # UTC date is Nov 6, but in the browser's timezone each is Nov 5 at night.
                "start_utc": f"2026-11-06T{utc_times[index]}:00+00:00",
                "stream_url": f"https://www.youtube.com/watch?v=night-race-{index}",
                "access": "unknown",
            }
            for index in range(7)
        ]
        with patch("collectors.live_now.db.get_events", return_value=saved_events), \
             patch("collectors.live_now.db.get_setting", return_value=None), \
             patch("collectors.live_now.db.set_setting") as save_setting:
            restored = live_now._merge_today_archive([], [], local_now)

        self.assertEqual(len(restored), 7)
        self.assertTrue(all(item["status"] == "scheduled_today" for item in restored))
        self.assertEqual(restored[0]["channel"], "GB3 Championship")
        archive = json.loads(save_setting.call_args.args[1])
        self.assertEqual(archive["date"], "2026-11-05")
        self.assertEqual(len(archive["items"]), 7)

    def test_schedule_hides_same_day_youtube_rows_but_keeps_tomorrow_and_other_sources(self):
        class FixedUtcDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                instant = datetime(2026, 11, 6, 1, 30, tzinfo=timezone.utc)
                return instant.astimezone(tz) if tz else instant

        events = [
            {
                "id": 1, "source": "youtube_scheduled", "external_id": "youtube:today",
                "name": "Today's late broadcast", "series": "Championship",
                "start_utc": "2026-11-06T01:45:00+00:00", "end_utc": None,
                "kind": "YouTube broadcast", "category": "Scheduled broadcast",
                "platform": "YouTube", "access": "unknown",
            },
            {
                "id": 2, "source": "youtube_scheduled", "external_id": "youtube:tomorrow",
                "name": "Tomorrow's broadcast", "series": "Championship",
                "start_utc": "2026-11-06T04:30:00+00:00", "end_utc": None,
                "kind": "YouTube broadcast", "category": "Scheduled broadcast",
                "platform": "YouTube", "access": "unknown",
            },
            {
                "id": 3, "source": "official_schedule", "external_id": "official:today",
                "name": "Official event entry", "series": "Championship",
                "start_utc": "2026-11-06T01:50:00+00:00", "end_utc": None,
                "kind": "Race", "category": "Race", "platform": "Official timing",
                "access": "unknown",
            },
        ]
        with patch("radar.datetime", FixedUtcDateTime), \
             patch("radar.db.purge_irrelevant_discoveries"), \
             patch("radar.db.get_events", return_value=events), \
             patch("radar.db.get_discoveries", return_value=[]), \
             patch("radar.db.get_setting", return_value=None):
            dashboard = radar.dashboard_data(local_tz=LOCAL_MINUS_3)

        self.assertEqual(
            {event["external_id"] for event in dashboard["events"]},
            {"youtube:tomorrow", "official:today"},
        )
        self.assertEqual(dashboard["local_date"], "2026-11-05")
        self.assertEqual(dashboard["stats"]["upcoming"], 2)


if __name__ == "__main__":
    unittest.main()
