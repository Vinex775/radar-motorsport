"""Multi-platform live + same-day scheduled broadcast scanner."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable

import db

from collectors.kick import search_live_streams as search_kick
from collectors.live_filter import classify_live_candidate
from collectors.twitch import search_live_streams as search_twitch
from collectors.youtube import search_live_videos
from collectors.youtube_upcoming import search_upcoming_videos

# Daily YouTube search.list budget:
# - Active streams: every 20 min = about 72 calls/day.
# - Upcoming streams: global + one verified official channel every 120 min
#   = about 24 calls/day. Combined estimate: 96 calls/day, below the default
#   100-call daily allowance. Do not add more channel searches without
#   increasing this TTL or reducing the active scan frequency.
SOURCE_TTLS = {
    "YouTube": 20 * 60,
    "YouTube scheduled": 120 * 60,
    "Twitch": 5 * 60,
    "Kick": 5 * 60,
}
_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
TODAY_ARCHIVE_SETTING = "youtube_scheduled_today_archive"


def _parse_schedule(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _merge_today_archive(current_items: list[dict], active_items: list[dict], local_now: datetime) -> list[dict]:
    """Persist same-day YouTube schedules so they remain visible after start time.

    YouTube may stop returning a scheduled broadcast from eventType=upcoming
    once its advertised start time has passed. Remembering today's discoveries
    lets APEX keep them visible with a verification warning until local midnight.
    """
    local_day = local_now.date().isoformat()
    try:
        raw = db.get_setting(TODAY_ARCHIVE_SETTING)
        stored = json.loads(raw) if raw else {}
        if not isinstance(stored, dict) or stored.get("date") != local_day:
            stored = {"date": local_day, "items": []}
    except Exception:
        stored = {"date": local_day, "items": []}

    by_url: dict[str, dict] = {}
    for item in stored.get("items", []):
        if isinstance(item, dict):
            key = str(item.get("url") or item.get("id") or "")
            if key:
                by_url[key] = dict(item)
    for item in current_items:
        scheduled = _parse_schedule(item.get("scheduled_start_at"))
        if not scheduled or scheduled.astimezone(local_now.tzinfo).date().isoformat() != local_day:
            continue
        key = str(item.get("url") or item.get("id") or "")
        if key:
            by_url[key] = dict(item)

    try:
        db.set_setting(TODAY_ARCHIVE_SETTING, json.dumps({"date": local_day, "items": list(by_url.values())}, ensure_ascii=False))
    except Exception:
        # A database write failure must not interrupt the live platform scan.
        pass

    active_urls = {
        str(item.get("url") or "")
        for item in active_items
        if item.get("status") == "live_now" and item.get("url")
    }
    now_utc = local_now.astimezone(timezone.utc)
    restored: list[dict] = []
    for item in by_url.values():
        url = str(item.get("url") or "")
        if url in active_urls:
            continue  # The active API result takes precedence over its scheduled record.
        scheduled = _parse_schedule(item.get("scheduled_start_at"))
        if not scheduled or scheduled.astimezone(local_now.tzinfo).date().isoformat() != local_day:
            continue
        copy = dict(item)
        copy["status"] = "scheduled_today" if scheduled > now_utc else "start_time_passed"
        copy["is_verified_live"] = False
        if copy["status"] == "start_time_passed":
            copy["note"] = (
                "The published start time has passed. YouTube has not confirmed that the broadcast started; "
                "it may be delayed or cancelled. Open the stream to verify."
            )
        restored.append(copy)
    return restored


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
    today_candidates: list[dict] = []
    future_events: list[dict] = []
    platforms: dict[str, dict] = {}
    local_now = datetime.now().astimezone()
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
                    if source == "YouTube scheduled":
                        today_candidates.append(item)
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
                    "official_channels_scanned": value.get("official_channels_scanned", 0),
                }
            except Exception as exc:
                platforms[source] = {
                    "configured": True,
                    "ok": False,
                    "count": 0,
                    "cached": False,
                    "message": f"{type(exc).__name__}: {exc}",
                }

    # Restore same-day scheduled broadcasts from local history. This keeps a
    # stream visible after its published start time even if YouTube drops it
    # from the upcoming search. Confirmed active results always take priority.
    active_items = [item for item in results if item.get("status") == "live_now"]
    active_urls = {str(item.get("url") or "") for item in active_items}
    results = [
        item for item in results
        if item.get("status") == "live_now" or str(item.get("url") or "") not in active_urls
    ]
    results.extend(_merge_today_archive(today_candidates, active_items, local_now))

    deduplicated: dict[tuple[str, str], dict] = {}
    for item in results:
        key = (str(item.get("platform") or ""), str(item.get("url") or item.get("id") or ""))
        deduplicated[key] = item
    merged = list(deduplicated.values())
    status_priority = {"live_now": 0, "scheduled_today": 1, "start_time_passed": 2}
    merged.sort(key=lambda item: (
        status_priority.get(item.get("status"), 3),
        item.get("scheduled_start_at") or "",
        -int(item.get("viewers") or 0),
        str(item.get("started_at") or item.get("published") or ""),
    ))

    active_count = sum(1 for item in merged if item.get("status") == "live_now")
    scheduled_today_count = sum(1 for item in merged if item.get("status") == "scheduled_today")
    start_time_passed_count = sum(1 for item in merged if item.get("status") == "start_time_passed")
    configured_count = sum(1 for name, item in platforms.items() if item["configured"] and name != "YouTube scheduled")
    if "YouTube scheduled" in platforms:
        scheduled_rows = [item for item in merged if item.get("platform") == "YouTube" and item.get("status") in {"scheduled_today", "start_time_passed"}]
        platforms["YouTube scheduled"]["count"] = len(scheduled_rows)
        platforms["YouTube scheduled"]["restored_today_count"] = sum(1 for item in scheduled_rows if item not in today_candidates)
        platforms["YouTube scheduled"]["start_time_passed_count"] = start_time_passed_count
    future_events.sort(key=lambda event: event.get("start_utc") or "")
    return {
        "mode": "live_now_today",
        "query": clean_query,
        "items": merged[:max_results],
        "count": len(merged),
        "active_count": active_count,
        "scheduled_today_count": scheduled_today_count,
        "start_time_passed_count": start_time_passed_count,
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
            "Live Now & Today prioritizes confirmed active streams, then YouTube broadcasts "
            "scheduled later today, and finally same-day schedules whose advertised start time "
            "has passed (shown for verification, not claimed as live). Tomorrow and later are "
            "routed to Schedule & Events. Twitch and Kick currently "
            "contribute active streams only. A scheduled page is not proof that the broadcast "
            "has started; access price and territorial availability must be checked at the destination."
        ),
    }
