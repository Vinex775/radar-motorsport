"""Discover YouTube livestreams scheduled for today or later.

Upcoming broadcasts scheduled for the computer's local date are surfaced in
Live Now as "Scheduled today". Broadcasts scheduled after today are converted
into Schedule & Events records. This is distinct from a championship session
calendar: it is evidence that a specific YouTube broadcast has been scheduled.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

from collectors.discovery import is_motorsport_result, is_reaction_or_commentary
from collectors.live_filter import classify_live_candidate
from collectors.youtube import SEARCH_API, _request_json, _video_details

# Keep the query broad and include terms needed to find official feeds whose
# titles do not contain the generic word "motorsport" (e.g. Porsche Cup / F1).
GLOBAL_UPCOMING_QUERY = (
    "motorsport|racing|F1|Formula 1|Porsche Cup|Carrera Cup|Sprint Challenge|"
    "karting|rally|rallye|rallycross|rally raid|autosuunnistus|rallisprint|"
    "autourheilu|moottoriurheilu|automobilismo|arrancada|automovilismo|"
    "motocross|supercross|enduro|speedway|drift|drag racing|hillclimb|"
    "autocross|time attack|stock car|NASCAR|IndyCar|MotoGP|WorldSBK|NHRA|"
    "GT3|DTM|BTCC|IMSA|WEC|Formula Drift|sprint car|ice racing|folkrace|"
    "autoslalom|tractor pulling|banger racing|short track racing|World of Outlaws"
)

# Some specialist championships do not use "motorsport" in the stream title.
# These exact series names are safe additional relevance signals.
SPECIALIST_SERIES_RE = re.compile(
    r"\b(?:porsche\s+(?:cup|carrera\s+cup|sprint\s+challenge)|carrera\s+cup|"
    r"sprint\s+challenge|gb3|eurocup\s*[- ]?3|f4\s+(?:brasil|brazil)|"
    r"moto1000gp|iame\s+(?:final\s+games|x30))\b",
    re.IGNORECASE,
)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _broadcast_record(video_id: str, title: str, channel: str, scheduled: datetime, url: str) -> dict:
    return {
        "external_id": f"youtube:{video_id}",
        "name": title,
        "series": channel or "YouTube motorsport channel",
        "category": "Scheduled broadcast",
        "kind": "YouTube broadcast",
        "start_utc": scheduled.isoformat(),
        "end_utc": None,
        "platform": "YouTube — scheduled broadcast",
        "access": "unknown",
        "stream_url": url,
        "watch_url": url,
        "region": "Global — territory and access to verify",
        "confidence": "platform_api",
        "source_name": channel or "YouTube",
        "source_url": url,
        "status": "upcoming",
        "youtube_scheduled_broadcast": True,
    }


def search_upcoming_videos(
    query: str = "",
    max_results: int = 50,
    now: datetime | None = None,
) -> dict:
    """Return YouTube broadcasts scheduled for today and future dates.

    The local date is taken from the machine running APEX. YouTube's
    scheduledStartTime is an ISO timestamp with an explicit offset and is
    converted to that local timezone before deciding which section receives it.
    """
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        return {
            "configured": False,
            "items": [],
            "future_events": [],
            "source": "youtube_upcoming",
            "message": "Set YOUTUBE_API_KEY to discover scheduled YouTube broadcasts.",
        }

    clean_query = (query or "").strip()
    if not clean_query or clean_query.lower() in {"motorsport", "all", "all motorsport", "live now"}:
        clean_query = GLOBAL_UPCOMING_QUERY
    if len(clean_query) > 500:
        clean_query = clean_query[:500]

    params = urlencode({
        "part": "snippet",
        "q": clean_query,
        "type": "video",
        "eventType": "upcoming",
        "maxResults": max(1, min(int(max_results), 50)),
        "order": "relevance",
        "safeSearch": "none",
        "key": api_key,
    })
    payload = _request_json(f"{SEARCH_API}?{params}", api_key)
    search_items = payload.get("items", []) or []
    video_ids = [str((item.get("id") or {}).get("videoId") or "") for item in search_items]
    details = _video_details([item for item in video_ids if item], api_key)

    if now is None:
        local_now = datetime.now().astimezone()
    elif now.tzinfo is None:
        local_now = now.astimezone()
    else:
        local_now = now
    today = local_now.date()
    utc_now = local_now.astimezone(timezone.utc)
    today_items: list[dict] = []
    future_events: list[dict] = []

    for search_item in search_items:
        video_id = str((search_item.get("id") or {}).get("videoId") or "")
        snippet = search_item.get("snippet") or {}
        if not video_id:
            continue
        detail = details.get(video_id) or {}
        detail_snippet = detail.get("snippet") or {}
        live_details = detail.get("liveStreamingDetails") or {}
        title = str(detail_snippet.get("title") or snippet.get("title") or "Scheduled live stream")
        description = str(detail_snippet.get("description") or snippet.get("description") or "")
        channel = str(detail_snippet.get("channelTitle") or snippet.get("channelTitle") or "YouTube channel")
        broadcast_state = detail_snippet.get("liveBroadcastContent") or snippet.get("liveBroadcastContent") or ""
        if broadcast_state and broadcast_state != "upcoming":
            continue

        scheduled = _parse_datetime(live_details.get("scheduledStartTime"))
        if not scheduled or scheduled <= utc_now:
            continue

        title_channel = f"{title} {channel}"
        if not (is_motorsport_result(title_channel, description) or SPECIALIST_SERIES_RE.search(title_channel)):
            continue
        if is_reaction_or_commentary(title, description):
            continue
        candidate = {
            "title": title,
            "description": description,
            "category": "Motorsport",
            "tags": detail_snippet.get("tags") or [],
        }
        keep, _reason = classify_live_candidate(candidate)
        if not keep:
            continue

        url = f"https://www.youtube.com/watch?v={video_id}"
        item = {
            "id": f"youtube:{video_id}",
            "external_id": f"youtube:{video_id}",
            "title": title,
            "description": description[:500],
            "channel": channel,
            "channel_id": detail_snippet.get("channelId") or snippet.get("channelId"),
            "published": detail_snippet.get("publishedAt") or snippet.get("publishedAt"),
            "scheduled_start_at": scheduled.isoformat(),
            "viewers": 0,
            "thumbnail": ((detail_snippet.get("thumbnails") or snippet.get("thumbnails") or {}).get("medium") or {}).get("url"),
            "url": url,
            "platform": "YouTube",
            "category": "Scheduled broadcast",
            "access": "unknown",
            "status": "scheduled_today" if scheduled.astimezone(local_now.tzinfo).date() == today else "scheduled_future",
            "is_verified_live": False,
            "verification": "YouTube Data API search.list eventType=upcoming + videos.list scheduledStartTime",
            "note": "YouTube confirms that this broadcast is scheduled. This does not prove that the video has started or that every session is included.",
        }
        if scheduled.astimezone(local_now.tzinfo).date() == today:
            today_items.append(item)
        else:
            future_events.append(_broadcast_record(video_id, title, channel, scheduled, url))

    today_items.sort(key=lambda item: item["scheduled_start_at"])
    future_events.sort(key=lambda item: item["start_utc"])
    return {
        "configured": True,
        "items": today_items,
        "future_events": future_events,
        "source": "youtube_upcoming",
        "query": clean_query,
        "search_results": len(search_items),
        "scheduled_today_count": len(today_items),
        "future_broadcast_count": len(future_events),
    }
