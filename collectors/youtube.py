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

from collectors.discovery import is_motorsport_result, is_reaction_or_commentary

API = "https://www.googleapis.com/youtube/v3/search"


GLOBAL_LIVE_QUERY = (
    "motorsport|racing|race|karting|rally|rallycross|rally raid|endurance|GT3|GT4|"
    "touring cars|stock cars|drift|drag racing|hillclimb|hill climb|speedway|"
    "motocross|supercross|enduro|superbike|motorcycle racing|sprint cars|"
    "autosuunnistus|rallisprint|ice racing|autocross|time attack|club racing|regional race"
)


def search_live_videos(query: str = "", max_results: int = 25) -> dict:
    """Return videos YouTube itself currently classifies as live.

    A broad scan is used when no meaningful query is supplied. YouTube's
    eventType=live is the only current-live assertion made by this collector.
    """
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        return {"configured": False, "items": [], "source": "youtube_data_api"}

    clean_query = (query or "").strip()
    if not clean_query or clean_query.lower() in {"motorsport", "all", "all motorsport", "live now"}:
        clean_query = GLOBAL_LIVE_QUERY

    params = urlencode({
        "part": "snippet",
        "q": clean_query[:400],
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
        raise RuntimeError(detail or f"YouTube API returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(f"Could not query YouTube: {exc}") from exc

    items = []
    for item in payload.get("items", []) or []:
        video_id = (item.get("id") or {}).get("videoId")
        snippet = item.get("snippet") or {}
        if not video_id:
            continue
        title = snippet.get("title") or "Live stream"
        description = snippet.get("description") or ""
        channel = snippet.get("channelTitle") or "YouTube channel"
        broadcast_state = snippet.get("liveBroadcastContent", "")
        # eventType=live is authoritative for this API query; still reject
        # obvious reacts/watch-alongs and non-motorsport search noise.
        if broadcast_state and broadcast_state != "live":
            continue
        if clean_query == GLOBAL_LIVE_QUERY:
            motorsport_evidence = f"{title} {channel}"
        else:
            # A user-entered championship/region is itself useful context for
            # small series whose stream title may omit the sport name.
            motorsport_evidence = f"{title} {channel} {clean_query}"
        if not is_motorsport_result(motorsport_evidence, description):
            continue
        if is_reaction_or_commentary(title, description):
            continue
        items.append({
            "title": title,
            "description": description[:400],
            "channel": channel,
            "channel_id": snippet.get("channelId"),
            "published": snippet.get("publishedAt"),
            "thumbnail": ((snippet.get("thumbnails") or {}).get("medium") or {}).get("url"),
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "platform": "YouTube",
            "access": "unknown",
            "status": "live_now",
            "is_verified_live": True,
            "verification": "YouTube Data API eventType=live",
            "note": "YouTube currently classifies this video as live. The race feed, channel legitimacy, access price, and regional restrictions still need verification.",
        })
    return {"configured": True, "items": items, "source": "youtube_data_api", "query": clean_query}
