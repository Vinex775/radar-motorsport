import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import radar
from collectors import official_schedule


class OfficialScheduleRegistryTests(unittest.TestCase):
    def test_registry_contains_verified_upcoming_series(self):
        events = official_schedule.fetch_official_schedule()
        ids = {event["external_id"] for event in events}
        self.assertGreaterEqual(len(events), 30)
        self.assertIn("f1-2026-sao-paulo-fp1-20261106", ids)
        self.assertIn("wec-bahrain-2026-weekend-20261106", ids)
        self.assertIn("motogp-qatar-2026-weekend-20261106", ids)
        self.assertIn("nascar-trucks-homestead-race-20261106", ids)
        self.assertIn("wec-2027-sao-paulo-6h", ids)
        self.assertTrue(all(event["source_url"].startswith("https://") for event in events))

    def test_registry_rejects_duplicate_ids(self):
        sample = {
            "events": [
                {"external_id": "same", "name": "Event A", "start": "2027-01-01T12:00:00Z", "source_url": "https://example.com/a", "confidence": "official"},
                {"external_id": "same", "name": "Event B", "start": "2027-01-02T12:00:00Z", "source_url": "https://example.com/b", "confidence": "official"},
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schedule.json"
            path.write_text(json.dumps(sample), encoding="utf-8")
            with patch.object(official_schedule, "REGISTRY_FILE", path):
                with self.assertRaisesRegex(ValueError, "Duplicate official schedule"):
                    official_schedule.fetch_official_schedule()

    def test_date_only_weekend_remains_visible_on_event_dates_and_expires_after(self):
        event = {
            "kind": "Race weekend — session times TBC",
            "start_utc": "2026-11-06T12:00:00+00:00",
            "end_utc": "2026-11-07T12:00:00+00:00",
        }
        self.assertEqual(radar.event_status(event, datetime(2026, 11, 6, 18, 0, tzinfo=timezone.utc)), "upcoming")
        self.assertEqual(radar.event_status(event, datetime(2026, 11, 8, 1, 0, tzinfo=timezone.utc)), "past")

    def test_refresh_runs_dtm_registry_and_discovery_independently(self):
        calls = []
        def fake_upsert(event, source):
            calls.append((event["external_id"], source))
        with patch.object(radar, "_run_dtm", return_value=([{"external_id": "dtm-1"}], None)), \
             patch.object(radar, "_run_official_schedule", return_value=([{"external_id": "official-1"}], None)), \
             patch.object(radar, "_run_discovery", return_value=([], None)), \
             patch.object(radar.db, "upsert_event", side_effect=fake_upsert), \
             patch.object(radar.db, "save_discoveries"), \
             patch.object(radar.db, "set_setting"):
            result = radar.refresh_all()
        self.assertEqual(result["events_updated"], 2)
        self.assertCountEqual(calls, [("dtm-1", "dtm"), ("official-1", "official_schedule")])
        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
