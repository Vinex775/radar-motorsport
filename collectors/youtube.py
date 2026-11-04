"""Find videos that YouTube currently classifies as active livestreams.

The global query uses YouTube's OR operator across motorsport disciplines and
multiple languages. One broad search request is used per cache interval to
respect the default search.list daily request limit.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from collectors.discovery import is_motorsport_result, is_reaction_or_commentary

API = "https://www.googleapis.com/youtube/v3"
SEARCH_API = f"{API}/search"
VIDEOS_API = f"{API}/videos"

# Google/YouTube supports Boolean OR (|) in q. Keep this under YouTube's
# query-length limit and include grassroots/local vocabulary, not only major
# championship names. Search.list is limited by the API's daily request cap.
GLOBAL_LIVE_QUERY = (
    'motorsport|racing|karting|rally|rallye|rallycross|'
    'rally raid|autosuunnistus|rallisprint|autourheilu|moottoriurheilu|'
    'automobilismo|arrancada|corrida de carros|automovilismo|rennen|bergrennen|'
    'course de cote|motocross|supercross|enduro|speedway|drift|'
    'drag racing|hillclimb|autocross|time attack|stock car|NASCAR|IndyCar|'
    'MotoGP|WorldSBK|NHRA|GT3|DTM|BTCC|IMSA|WEC|iRacing|sim racing|'
    'Formula Drift|sprint car|ice racing|folkrace|rallysprint|autoslalom|'
    'tractor pulling|banger racing|short track racing'
)


def _request_json(url: str, api_key: str) -> dict:
    request = Request(url, headers={"User-Agent": "APEX-Motorsport-Radar/1.4"})
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            detail = ""
        # Never expose the full URL because it contains the API key.
        raise RuntimeError(detail or f"YouTube API returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(f"Could not query YouTube: {exc}") from exc


def _video_details(video_ids: list[str], api_key: str) -> dict[str, dict]:
    if not video_ids:
        return {}
    params = urlencode({
        "part": "snippet,liveStreamingDetails",
        "id": ",".join(video_ids[:50]),
        "key": api_key,
    })
    try:
        payload = _request_json(f"{VIDEOS_API}?{params}", api_key)
    except RuntimeError:
        # Search.list already verified eventType=live. Details are enrichment;
        # a temporary videos.list failure must not discard every live result.
        return {}
    return {
        str(item.get("id")): item
        for item in (payload.get("items") or [])
        if item.get("id")
    }


def search_live_videos(query: str = "", max_results: int = 50) -> dict:
    """Return active YouTube broadcasts, never upcoming or completed videos."""
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        return {
            "configured": False,
            "items": [],
            "source": "youtube",
            "message": "Set YOUTUBE_API_KEY to enable API-verified YouTube Live discovery.",
        }

    clean_query = (query or "").strip()
    if not clean_query or clean_query.lower() in {"motorsport", "all", "all motorsport", "live now"}:
        clean_query = GLOBAL_LIVE_QUERY
    if len(clean_query) > 500:
        clean_query = clean_query[:500]

    params = urlencode({
        "part": "snippet",
        "q": clean_query,
        "type": "video",
        "eventType": "live",
        "maxResults": max(1, min(int(max_results), 50)),
        "order": "relevance",
        "safeSearch": "none",
        "key": api_key,
    })
    payload = _request_json(f"{SEARCH_API}?{params}", api_key)
    search_items = payload.get("items", []) or []
    video_ids = [str((item.get("id") or {}).get("videoId") or "") for item in search_items]
    details = _video_details([value for value in video_ids if value], api_key)

    items: list[dict] = []
    for item in search_items:
        video_id = str((item.get("id") or {}).get("videoId") or "")
        snippet = item.get("snippet") or {}
        if not video_id:
            continue
        detail = details.get(video_id) or {}
        detail_snippet = detail.get("snippet") or {}
        live_details = detail.get("liveStreamingDetails") or {}
        title = str(detail_snippet.get("title") or snippet.get("title") or "Live stream")
        description = str(detail_snippet.get("description") or snippet.get("description") or "")
        channel = str(detail_snippet.get("channelTitle") or snippet.get("channelTitle") or "YouTube channel")
        broadcast_state = detail_snippet.get("liveBroadcastContent") or snippet.get("liveBroadcastContent") or ""
        # Drop a video if it stopped broadcasting between search and detail lookup.
        if broadcast_state and broadcast_state != "live":
            continue
        query_evidence = "" if clean_query == GLOBAL_LIVE_QUERY else clean_query
        if not is_motorsport_result(f"{title} {channel} {query_evidence}", description):
            continue
        if is_reaction_or_commentary(title, description):
            continue
        items.append({
            "id": f"youtube:{video_id}",
            "title": title,
            "description": description[:500],
            "channel": channel,
            "channel_id": detail_snippet.get("channelId") or snippet.get("channelId"),
            "published": detail_snippet.get("publishedAt") or snippet.get("publishedAt"),
            "started_at": live_details.get("actualStartTime"),
            "viewers": int(live_details.get("concurrentViewers") or 0),
            "thumbnail": ((detail_snippet.get("thumbnails") or snippet.get("thumbnails") or {}).get("medium") or {}).get("url"),
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "platform": "YouTube",
            "category": "Motorsport",
            "access": "unknown",
            "status": "live_now",
            "is_verified_live": True,
            "verification": "YouTube Data API search.list eventType=live",
            "note": "YouTube currently classifies this video as live. The race feed, channel legitimacy, access price, and regional restrictions still need verification.",
        })

    return {
        "configured": True,
        "items": items,
        "source": "youtube",
        "query": clean_query,
        "search_results": len(search_items),
    }
