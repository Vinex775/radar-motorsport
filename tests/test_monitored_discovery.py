import unittest
from unittest.mock import patch

from collectors import monitored_discovery


class MonitoredDiscoveryTests(unittest.TestCase):
    def test_targeted_results_keep_the_monitoring_source(self):
        source = {
            "id": "porsche-cup-brasil",
            "name": "Porsche Cup Brasil",
            "discovery_query": "site:porsche.com Porsche Cup",
        }
        parsed_item = {
            "id": "lead-1",
            "title": "Porsche Cup confirms 2027 calendar",
            "summary": "Future Porsche Carrera Cup schedule for 2027.",
            "url": "https://news.example/porsche-2027",
            "published": "2026-11-05T10:00:00+00:00",
            "source_name": "Motorsport News",
            "lead_status": "upcoming_lead",
            "note": "Future lead.",
        }
        with patch.object(monitored_discovery, "get_discovery_sources", return_value=[source]), \
             patch.object(monitored_discovery, "_fetch_query", return_value=b"<rss />"), \
             patch.object(monitored_discovery, "_parse_feed", return_value=[dict(parsed_item)]):
            results = monitored_discovery.discover_monitored_source_leads()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["monitoring_source_id"], "porsche-cup-brasil")
        self.assertIn("Porsche Cup Brasil", results[0]["source_name"])


if __name__ == "__main__":
    unittest.main()
