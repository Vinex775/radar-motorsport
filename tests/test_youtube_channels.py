import unittest
from io import BytesIO
from unittest.mock import patch

from collectors.youtube_channels import _read_channel_feed


ATOM_FEED = '''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015">
  <entry>
    <id>yt:video:abc123</id>
    <yt:videoId>abc123</yt:videoId>
    <yt:channelId>UCexample123</yt:channelId>
    <title>Official race broadcast — upcoming</title>
    <published>2026-11-05T12:00:00+00:00</published>
  </entry>
</feed>'''.encode('utf-8')


class YouTubeChannelFeedTests(unittest.TestCase):
    def test_reads_channel_feed_without_spending_search_list_quota(self):
        source = {
            "name": "Example official channel",
            "youtube_channel": {"channel_id": "UCexample123"}
        }
        with patch("collectors.youtube_channels.urlopen", return_value=BytesIO(ATOM_FEED)) as open_feed:
            items, error = _read_channel_feed(source, "not-used-with-direct-id", 12)
        self.assertIsNone(error)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"]["videoId"], "abc123")
        self.assertEqual(items[0]["snippet"]["channelId"], "UCexample123")
        self.assertIn("feeds/videos.xml", open_feed.call_args.args[0].full_url)

    def test_feed_failure_is_isolated_to_that_channel(self):
        source = {
            "name": "Unavailable channel",
            "youtube_channel": {"channel_id": "UCexample123"}
        }
        with patch("collectors.youtube_channels.urlopen", side_effect=OSError("offline")):
            items, error = _read_channel_feed(source, "unused", 12)
        self.assertEqual(items, [])
        self.assertIn("Unavailable channel", error)


if __name__ == "__main__":
    unittest.main()
