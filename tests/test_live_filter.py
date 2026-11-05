import unittest
from collectors.live_filter import classify_live_candidate


class LiveCandidateFilterTests(unittest.TestCase):
    def test_rejects_24_7_replay_compilations(self):
        for title in (
            "Non-Stop Canadian Rally Action RAW Sound 24/7 #rally #racing",
            "Best of WRC Rally | RAW Sound HD",
            "Historic race replay from 2019",
        ):
            with self.subTest(title=title):
                self.assertEqual(classify_live_candidate({"title": title}), (False, "replay_or_loop"))

    def test_does_not_reject_endurance_24_hour_race(self):
        self.assertEqual(
            classify_live_candidate({"title": "Live: 24 Hours of Le Mans — race start"}),
            (True, None),
        )

    def test_rejects_known_racing_games(self):
        examples = (
            {"title": "Ranked lobby", "category": "Forza Motorsport"},
            {"title": "Sonic Racing: CrossWorlds", "category": "Sonic Racing: CrossWorlds"},
            {"title": "Motorsport Manager career mode", "category": "Motorsport Manager"},
            {"title": "Live gameplay", "category": "Racing"},
        )
        for item in examples:
            with self.subTest(item=item):
                self.assertEqual(classify_live_candidate(item), (False, "video_game"))

    def test_keeps_physical_motorsport_stream(self):
        item = {
            "title": "Swedish Karting Championship — Race 2 LIVE",
            "channel": "Regional Karting TV",
            "category": "Motorsports",
            "description": "Live coverage from the circuit.",
        }
        self.assertEqual(classify_live_candidate(item), (True, None))




if __name__ == "__main__":
    unittest.main()
