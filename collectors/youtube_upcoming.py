"""Discover YouTube livestreams scheduled for today or later.

Global eventType=upcoming search is supplemented by channel-scoped searches
for official motorsport broadcasters. This catches broadcasts that YouTube's
global relevance ranking omits (for example, a Porsche Cup Brasil stream).
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

from collectors.discovery import is_motorsport_result, is_reaction_or_commentary
from collectors.live_filter import classify_live_candidate
from collectors.youtube import SEARCH_API, _request_json, _video_details

GLOBAL_UPCOMING_QUERY = (
    "motorsport|racing|F1|Formula 1|Porsche Cup|Carrera Cup|Sprint Challenge|"
    "karting|rally|rallye|rallycross|rally raid|autosuunnistus|rallisprint|"
    "autourheilu|moottoriurheilu|automobilismo|arrancada|automovilismo|"
    "motocross|supercross|enduro|speedway|drift|drag racing|hillclimb|"
    "autocross|time attack|stock car|NASCAR|IndyCar|MotoGP|WorldSBK|NHRA|"
    "GT3|DTM|BTCC|IMSA|WEC|Formula Drift|sprint car|ice racing|folkrace|"
    "autoslalom|tractor pulling|banger racing|short track racing|World of Outlaws"
)

SPECIALIST_SERIES_RE = re.compile(
    r"\b(?:porsche\s+(?:cup|carrera\s+cup|sprint\s+challenge)|carrera\s+cup|"
    r"sprint\s+challenge|gb3|eurocup\s*[- ]?3|f4\s+(?:brasil|brazil)|"
    r"moto1000gp|iame\s+(?:final\s+games|x30))\b",
    re.IGNORECASE,
)

# Official channel IDs are more reliable than global search ranking. Add new
# entries only after verifying that the channel belongs to the championship.
OFFICIAL_UPCOMING_CHANNELS = (
    {
        "channel_id": "UCwiRFcstDPKaCiOTXuoFhrQ",
        "name": "Porsche Cup Brasil",
    },
)

# One-time bootstrap from the official Porsche Cup broadcast page supplied by
# the user. This preserves the 5 Nov 2026 programme even when YouTube stops
# returning it from eventType=upcoming after its scheduled start time.
# It expires automatically after the local date; future entries are discovered
# through the API and persisted locally by collectors.live_now.
KNOWN_SAME_DAY_BROADCASTS = (
    {
        "local_date": "2026-11-05",
        "video_id": "BFHxCOvY2Zw",
        "title": "ET.9 | INTERLAGOS (F1) | QUALI - SPRINT CHALLENGE | TEMPORADA 2026",
        "channel": "Porsche Cup Brasil",
        "channel_id": "UCwiRFcstDPKaCiOTXuoFhrQ",
        "scheduled_start_at": "2026-11-05T19:30:00+00:00",
        "note": "Official Porsche Cup Brasil scheduled broadcast. The scheduled start time has passed; open the stream to verify whether it started, was delayed or was cancelled.",
    },
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


def _search_upcoming(
    api_key: str,
    max_results: int,
    query: str | None = None,
    channel_id: str | None = None,
) -> list[dict]:
    params = {
        "part": "snippet",
        "type": "video",
        "eventType": "upcoming",
        "maxResults": max(1, min(int(max_results), 50)),
        "order": "relevance",
        "safeSearch": "none",
        "key": api_key,
    }
    if query:
        params["q"] = query
    if channel_id:
        params["channelId"] = channel_id
    payload = _request_json(f"{SEARCH_API}?{urlencode(params)}", api_key)
    return payload.get("items", []) or []


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

    The global search is combined with verified official channel searches.
    Channel-scoped results are prioritized before the global results so a
    highly relevant official broadcast cannot be pushed out of the 50-video
    detail lookup by unrelated worldwide results.
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

    # Query official channels independently of global search relevance. A
    # channel query has no q restriction: all upcoming broadcasts from that
    # verified championship channel can be inspected and classified.
    prioritized_items: dict[str, dict] = {}
    official_search_results = 0
    channel_search_errors: list[str] = []
    for channel in OFFICIAL_UPCOMING_CHANNELS:
        try:
            channel_items = _search_upcoming(
                api_key,
                max_results,
                channel_id=channel["channel_id"],
            )
            official_search_results += len(channel_items)
            for item in channel_items:
                video_id = str((item.get("id") or {}).get("videoId") or "")
                if video_id:
                    prioritized_items[video_id] = item
        except RuntimeError as exc:
            # An individual official channel must not disable global discovery.
            channel_search_errors.append(f"{channel['name']}: {exc}")

    global_items = _search_upcoming(api_key, max_results, query=clean_query)
    search_items_by_id = dict(prioritized_items)
    for item in global_items:
        video_id = str((item.get("id") or {}).get("videoId") or "")
        if video_id and video_id not in search_items_by_id:
            search_items_by_id[video_id] = item

    # Detail lookups are limited to 50 IDs per request. The official channel
    # results are inserted first so they retain priority within that limit.
    search_items = list(search_items_by_id.values())[:max(1, min(int(max_results), 50))]
    video_ids = [
        str((item.get("id") or {}).get("videoId") or "")
        for item in search_items
    ]
    details = _video_details([value for value in video_ids if value], api_key)

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
        if broadcast_state and broadcast_state not in {"upcoming", "live"}:
            continue

        scheduled = _parse_datetime(live_details.get("scheduledStartTime"))
        if not scheduled:
            continue
        local_scheduled = scheduled.astimezone(local_now.tzinfo)
        if local_scheduled.date() < today:
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
            "status": (
                "live_now" if broadcast_state == "live" else
                "scheduled_today" if local_scheduled.date() == today and scheduled > utc_now else
                "start_time_passed" if local_scheduled.date() == today else
                "scheduled_future"
            ),
            "is_verified_live": broadcast_state == "live",
            "verification": "YouTube Data API eventType=upcoming + official channel search + videos.list scheduledStartTime",
            "note": (
                "YouTube reports this broadcast as live. Verify that the player is showing the actual race feed."
                if broadcast_state == "live" else
                "YouTube confirms the broadcast schedule. The scheduled start time has passed, but the platform has not confirmed that the stream started; open it to verify."
                if local_scheduled.date() == today and scheduled <= utc_now else
                "YouTube confirms that this broadcast is scheduled. This does not prove that the video has started or that every session is included."
            ),
        }
        if local_scheduled.date() == today:
            today_items.append(item)
        else:
            future_events.append(_broadcast_record(video_id, title, channel, scheduled, url))

    # Keep the user's confirmed Porsche Cup programme visible for its local
    # event date even if YouTube removes it from its upcoming search after the
    # advertised start. This seed is date-scoped and expires automatically.
    for known in KNOWN_SAME_DAY_BROADCASTS:
        if known["local_date"] != today.isoformat():
            continue
        if any(item.get("id") == f"youtube:{known['video_id']}" for item in today_items):
            continue
        scheduled = _parse_datetime(known["scheduled_start_at"])
        if not scheduled:
            continue
        status = "scheduled_today" if scheduled > utc_now else "start_time_passed"
        today_items.append({
            "id": f"youtube:{known['video_id']}",
            "external_id": f"youtube:{known['video_id']}",
            "title": known["title"],
            "description": known["note"],
            "channel": known["channel"],
            "channel_id": known["channel_id"],
            "scheduled_start_at": scheduled.isoformat(),
            "viewers": 0,
            "url": f"https://www.youtube.com/watch?v={known['video_id']}",
            "platform": "YouTube",
            "category": "Scheduled broadcast",
            "access": "unknown",
            "status": status,
            "is_verified_live": False,
            "verification": "User-supplied official Porsche Cup Brasil schedule screenshot and direct video link",
            "note": known["note"],
        })

    status_priority = {"live_now": 0, "scheduled_today": 1, "start_time_passed": 2}
    today_items.sort(key=lambda item: (
        status_priority.get(item.get("status"), 3),
        item.get("scheduled_start_at", ""),
    ))
    future_events.sort(key=lambda item: item["start_utc"])
    result = {
        "configured": True,
        "items": today_items,
        "future_events": future_events,
        "source": "youtube_upcoming",
        "query": clean_query,
        "search_results": len(global_items) + official_search_results,
        "scheduled_today_count": sum(item.get("status") == "scheduled_today" for item in today_items),
        "start_time_passed_count": sum(item.get("status") == "start_time_passed" for item in today_items),
        "active_count": sum(item.get("status") == "live_now" for item in today_items),
        "future_broadcast_count": len(future_events),
        "official_channels_scanned": len(OFFICIAL_UPCOMING_CHANNELS) - len(channel_search_errors),
    }
    if channel_search_errors:
        result["message"] = "Some official channel searches failed: " + " | ".join(channel_search_errors)
    return result
