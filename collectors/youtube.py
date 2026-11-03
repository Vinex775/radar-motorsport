"""Search for videos that the YouTube Data API currently identifies as live streams.

The API key is optional and should be supplied through an environment variable so it is not
stored in the repository.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://www.googleapis.com/youtube/v3/search"


def search_live_videos(query: str, max_results: int = 25) -> dict:
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        return {"configured": False, "items": []}

    params = urlencode({
        "part": "snippet",
        "q": query[:150],
        "type": "video",
        "eventType": "live",
        "maxResults": max(1, min(int(max_results), 25)),
        "order": "relevance",
        "key": api_key,
    })
    request = Request(API + "?" + params, headers={"User-Agent": "MotorsportRadar/1.0"})
    try:
        with urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        # Do not expose the request URL because it contains the API key.
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            detail = ""
        raise RuntimeError(detail or f"YouTube API respondeu HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(f"Could not query YouTube: {exc}") from exc

    items = []
    for item in payload.get("items", []) or []:
        video_id = (item.get("id") or {}).get("videoId")
        snippet = item.get("snippet") or {}
        if not video_id:
            continue
        items.append({
            "title": snippet.get("title") or "Live stream",
            "channel": snippet.get("channelTitle") or "YouTube channel",
            "published": snippet.get("publishedAt"),
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "platform": "YouTube",
            "access": "unknown",
            "is_verified_live": True,
            "note": "YouTube currently marks this video as live. Access price and regional restrictions still need to be confirmed.",
        })
    return {"configured": True, "items": items}
