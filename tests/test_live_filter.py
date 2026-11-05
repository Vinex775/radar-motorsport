import io
import unittest
from urllib.error import HTTPError
from email.message import Message
from unittest.mock import patch

from collectors.live_filter import classify_live_candidate
from collectors import kick


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
        self.assertEqual(classify_live_candidate({"title": "Live: 24 Hours of Le Mans — race start"}), (True, None))

    def test_rejects_known_racing_games(self):
        examples = (
            {"title": "Ranked lobby", "category": "Forza Motorsport"},
            {"title": "Sonic Racing: CrossWorlds", "category": "Sonic Racing: CrossWorlds"},
            {"title": "Motorsport Manager career mode", "category": "Motorsport Manager"},
            {"title": "KR* Burst 2F", "category": "Racing Master"},
            {"title": "Live gameplay", "category": "Racing"},
            {"title": "Descent", "category": "Racing"},
            {"title": "just chatting then game", "category": "Descent"},
        )
        for item in examples:
            with self.subTest(item=item):
                self.assertEqual(classify_live_candidate(item), (False, "video_game"))

    def test_rejects_ps1_racing_games_and_racing_lagoon(self):
        item = {"title": "PS1 Racing Games! [ENG/KHM]", "category": "Racing Lagoon"}
        self.assertEqual(classify_live_candidate(item), (False, "video_game"))

    def test_rejects_generic_game_wording_even_when_category_is_racing(self):
        examples = (
            {"title": "Classic racing games from the PS2 era", "category": "Racing"},
            {"title": "PlayStation 1 retro gaming", "category": "Auto Racing"},
            {"title": "Playing games tonight", "category": "Racing"},
        )
        for item in examples:
            with self.subTest(item=item):
                self.assertEqual(classify_live_candidate(item), (False, "video_game"))

    def test_rejects_generic_racing_category_without_event_evidence(self):
        self.assertEqual(
            classify_live_candidate({"title": "Just hanging out", "category": "Auto Racing"}),
            (False, "insufficient_motorsport_evidence"),
        )
        self.assertEqual(
            classify_live_candidate({"title": "descent", "category": "Racing", "channel": "jahn3369"}),
            (False, "video_game"),
        )

    def test_accepts_generic_category_with_specific_race_evidence(self):
        item = {"title": "Swedish Karting Championship — Race 2 LIVE", "category": "Racing"}
        self.assertEqual(classify_live_candidate(item), (True, None))

    def test_rejects_track_construction_and_other_support_work(self):
        examples = (
            {"title": "I-500 Track Construction", "category": "Snowmobile Racing"},
            {"title": "Snowmobile raceway maintenance", "category": "Snowmobile Racing"},
            {"title": "Building the circuit", "category": "Motorsport"},
        )
        for item in examples:
            with self.subTest(item=item):
                self.assertEqual(classify_live_candidate(item), (False, "non_race_support_activity"))

    def test_keeps_physical_motorsport_stream(self):
        item = {
            "title": "Swedish Karting Championship — Race 2 LIVE",
            "channel": "Regional Karting TV",
            "category": "Motorsports",
            "description": "Live coverage from the circuit.",
        }
        self.assertEqual(classify_live_candidate(item), (True, None))


class KickDiagnosticTests(unittest.TestCase):
    def test_distinguishes_oauth_403_and_includes_cloudflare_ray(self):
        headers = Message()
        headers["CF-Ray"] = "example-ray-id"
        error = HTTPError("https://id.kick.com/oauth/token", 403, "Forbidden", headers,
                          io.BytesIO(b"<html><title>Forbidden</title><body>Access denied</body></html>"))
        with patch("collectors.kick.urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "Kick OAuth token endpoint returned HTTP 403") as caught:
                kick._request_json("https://id.kick.com/oauth/token", context="OAuth token endpoint")
        self.assertIn("Cloudflare Ray ID: example-ray-id", str(caught.exception))

    def test_distinguishes_kick_api_endpoint_403(self):
        error = HTTPError("https://api.kick.com/public/v2/categories", 403, "Forbidden", Message(),
                          io.BytesIO(b'{"message":"Access denied"}'))
        with patch("collectors.kick.urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "Kick API endpoint /public/v2/categories returned HTTP 403") as caught:
                kick._request_json("https://api.kick.com/public/v2/categories", context="API endpoint /public/v2/categories")
        self.assertIn("Access denied", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
