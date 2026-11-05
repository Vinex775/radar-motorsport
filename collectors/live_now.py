"""Multi-platform live + same-day scheduled broadcast scanner."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Callable

from collectors.kick import search_live_streams as search_kick
from collectors.live_filter import classify_live_candidate
from collectors.twitch import search_live_streams as search_twitch
from collectors.youtube import search_live_videos
from collectors.youtube_upcoming import search_upcoming_videos

# Keep YouTube's two search.list calls below the default 100-call daily bucket:
# active broadcasts refresh every 20 min (about 72/day); scheduled broadcasts
# refresh every 90 min (about 16/day). Twitch and Kick stay at 5 min.
SOURCE_TTLS = {
    "YouTube": 20 * 60,
    "YouTube scheduled": 90 * 60,
    "Twitch": 5 * 60,
    "Kick": 5 * 60,
}
_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}


def _run_cached(source: str, query_key: str, fetch: Callable[[], dict]) -> dict:
    key = (source, query_key)
    now = time.monotonic()
    cached = _CACHE.get(key)
    ttl = SOURCE_TTLS[source]
    if cached and now - cached[0] < ttl:
        value = dict(cached[1])
        value["cached"] = True
        return value
    value = fetch()
    value["cached"] = False
    if value.get("configured") and not value.get("error"):
        _CACHE[key] = (now, dict(value))
    return value


def search_all_live_streams(query: str = "motorsport", max_results: int = 300) -> dict:
    """Return active streams, today's scheduled YouTube broadcasts and later broadcasts for Schedule."""
    clean_query = (query or "motorsport").strip()[:180] or "motorsport"
    global_scan = clean_query.lower() in {"motorsport", "all", "all motorsport", "live now"}
    youtube_key = "global" if global_scan else clean_query.casefold()
    local_day_key = datetime.now().astimezone().date().isoformat()

    results: list[dict] = []
    future_events: list[dict] = []
    platforms: dict[str, dict] = {}
    collectors = {
        "YouTube": (lambda: search_live_videos("motorsport" if global_scan else clean_query, max_results=50), youtube_key),
        "YouTube scheduled": (
            lambda: search_upcoming_videos("motorsport" if global_scan else clean_query, max_results=50),
            f"{youtube_key}:{local_day_key}",
        ),
        "Twitch": (lambda: search_twitch(max_results=max_results), "global"),
        "Kick": (lambda: search_kick(max_results=max_results), "global"),
    }

    with ThreadPoolExecutor(max_workers=len(collectors)) as pool:
        future_sources = {
            pool.submit(_run_cached, source, query_key, fetch): source
            for source, (fetch, query_key) in collectors.items()
        }
        for future in as_completed(future_sources):
            source = future_sources[future]
            try:
                value = future.result()
                items = value.get("items") or []
                kept_count = 0
                rejected = {
                    "replay_or_loop": 0,
                    "video_game": 0,
                    "non_race_support_activity": 0,
                    "insufficient_motorsport_evidence": 0,
                }
                for item in items:
                    keep, reason = classify_live_candidate(item)
                    if not keep:
                        if reason in rejected:
                            rejected[reason] += 1
                        continue
                    item.setdefault("platform", "YouTube" if source == "YouTube scheduled" else source)
                    item.setdefault("access", "unknown")
                    item.setdefault("status", "scheduled_today" if source == "YouTube scheduled" else "live_now")
                    item.setdefault("is_verified_live", item["status"] == "live_now")
                    results.append(item)
                    kept_count += 1

                if source == "YouTube scheduled":
                    for event in value.get("future_events") or []:
                        candidate = {
                            "title": event.get("name", ""),
                            "description": event.get("series", ""),
                            "category": "Scheduled broadcast",
                        }
                        keep, reason = classify_live_candidate(candidate)
                        if keep:
                            future_events.append(event)
                        elif reason in rejected:
                            rejected[reason] += 1

                filtered_count = sum(rejected.values())
                base_message = value.get("message") or value.get("error") or ("Connected" if value.get("configured") else "Not configured")
                if filtered_count:
                    base_message += (
                        f". Excluded {rejected['replay_or_loop']} replay/loop, "
                        f"{rejected['video_game']} video-game, "
                        f"{rejected['non_race_support_activity']} non-race support, and "
                        f"{rejected['insufficient_motorsport_evidence']} weak-evidence stream(s)."
                    )
                platforms[source] = {
                    "configured": bool(value.get("configured")),
                    "ok": bool(value.get("configured")) and not value.get("error"),
                    "count": kept_count,
                    "raw_count": len(items),
                    "filtered": rejected,
                    "filtered_count": filtered_count,
                    "cached": bool(value.get("cached")),
                    "message": base_message,
                    "categories_scanned": value.get("categories_scanned"),
                    "future_broadcast_count": len(value.get("future_events") or []),
                }
            except Exception as exc:
                platforms[source] = {
                    "configured": True,
                    "ok": False,
                    "count": 0,
                    "cached": False,
                    "message": f"{type(exc).__name__}: {exc}",
                }

    deduplicated: dict[tuple[str, str], dict] = {}
    for item in results:
        key = (str(item.get("platform") or ""), str(item.get("url") or item.get("id") or ""))
        deduplicated[key] = item
    merged = list(deduplicated.values())
    merged.sort(key=lambda item: (
        item.get("status") == "scheduled_today",
        item.get("scheduled_start_at") or "",
        -int(item.get("viewers") or 0),
        str(item.get("started_at") or item.get("published") or ""),
    ))

    active_count = sum(1 for item in merged if item.get("status") == "live_now")
    scheduled_today_count = sum(1 for item in merged if item.get("status") == "scheduled_today")
    configured_count = sum(1 for name, item in platforms.items() if item["configured"] and name != "YouTube scheduled")
    future_events.sort(key=lambda event: event.get("start_utc") or "")
    return {
        "mode": "live_now_today",
        "query": clean_query,
        "items": merged[:max_results],
        "count": len(merged),
        "active_count": active_count,
        "scheduled_today_count": scheduled_today_count,
        "future_events": future_events,
        "platforms": platforms,
        "configured_sources": configured_count,
        "scanned_at": time.time(),
        "refresh_policy": {
            "youtube_minutes": SOURCE_TTLS["YouTube"] // 60,
            "youtube_scheduled_minutes": SOURCE_TTLS["YouTube scheduled"] // 60,
            "other_platforms_minutes": SOURCE_TTLS["Twitch"] // 60,
        },
        "note": (
            "Live Now includes platform-confirmed active broadcasts and YouTube broadcasts "
            "scheduled to start today in the computer's local timezone. YouTube broadcasts "
            "scheduled after today are routed to Schedule & Events. Twitch and Kick currently "
            "contribute active streams only. A scheduled page is not proof that the broadcast "
            "has started; access price and territorial availability must be checked at the destination."
        ),
    }
