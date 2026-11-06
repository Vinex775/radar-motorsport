import unittest
from datetime import datetime, timezone

from collectors.youtube_channel_discovery import build_channel_discovery_leads


class YouTubeChannelDiscoveryTests(unittest.TestCase):
    def test_future_calendar_video_from_monitored_channel_becomes_discovery_lead(self):
        next_season = datetime.now(timezone.utc).year + 1
        published = datetime.now(timezone.utc).isoformat()
        channel_items = [{
            "id": {"videoId": "future123"},
            "snippet": {
                "title": f"Porsche Cup Brasil confirms {next_season} calendar",
                "channelTitle": "Porsche Cup Brasil",
                "publishedAt": published,
                "monitoringSourceId": "porsche-cup-brasil",
                "monitoringSourceName": "Porsche Cup Brasil",
                "monitoringSeries": ["Porsche Carrera Cup Brasil", "Porsche Sprint Challenge Brasil"],
            },
        }]
        details = {
            "future123": {
                "snippet": {
                    "title": f"Porsche Cup Brasil confirms {next_season} calendar",
                    "description": f"The official calendar for the {next_season} season has been announced.",
                    "publishedAt": published,
                    "channelTitle": "Porsche Cup Brasil",
                }
            }
        }
        leads = build_channel_discovery_leads(channel_items, details)
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["lead_status"], "upcoming_lead")
        self.assertEqual(leads[0]["series"], "Porsche Carrera Cup Brasil")
        self.assertIn("monitored official channel", leads[0]["source_name"])
        self.assertFalse(leads[0]["is_verified_live"])

    def test_post_event_highlights_do_not_become_future_leads(self):
        next_season = datetime.now(timezone.utc).year + 1
        published = datetime.now(timezone.utc).isoformat()
        channel_items = [{
            "id": {"videoId": "recap123"},
            "snippet": {
                "title": f"Porsche Cup {next_season} season highlights",
                "channelTitle": "Porsche Cup Brasil",
                "publishedAt": published,
                "monitoringSourceName": "Porsche Cup Brasil",
                "monitoringSeries": ["Porsche Carrera Cup Brasil"],
            },
        }]
        details = {
            "recap123": {
                "snippet": {
                    "title": f"Porsche Cup {next_season} season highlights",
                    "description": "Highlights from the race.",
                    "publishedAt": published,
                    "channelTitle": "Porsche Cup Brasil",
                }
            }
        }
        self.assertEqual(build_channel_discovery_leads(channel_items, details), [])


if __name__ == "__main__":
    unittest.main()
