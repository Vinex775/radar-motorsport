"""Multi-platform live scanner with per-source cache windows."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from collectors.kick import search_live_streams as search_kick
from collectors.twitch import search_live_streams as search_twitch
from collectors.youtube import search_live_videos

# YouTube search.list has a default daily request cap. Keep the global scan to
# one broad request and cache it for 20 minutes; Twitch/Kick can be polled more
# frequently without spending the YouTube search quota.
SOURCE_TTLS = {"YouTube": 20 * 60, "Twitch": 5 * 60, "Kick": 5 * 60}
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
    """Scan every configured live API and merge active motorsport broadcasts."""
    clean_query = (query or "motorsport").strip()[:180] or "motorsport"
    global_scan = clean_query.lower() in {"motorsport", "all", "all motorsport", "live now"}
    youtube_key = "global" if global_scan else clean_query.casefold()

    results: list[dict] = []
    platforms: dict[str, dict] = {}
    collectors = {
        "YouTube": (lambda: search_live_videos("motorsport" if global_scan else clean_query, max_results=50), youtube_key),
        "Twitch": (lambda: search_twitch(max_results=max_results), "global"),
        "Kick": (lambda: search_kick(max_results=max_results), "global"),
    }

    # Scan all configured providers at the same time. A slow Twitch category
    # lookup must not make YouTube or Kick results wait behind it.
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
                for item in items:
                    item.setdefault("platform", source)
                    item.setdefault("access", "unknown")
                    item.setdefault("status", "live_now")
                    item.setdefault("is_verified_live", True)
                    results.append(item)
                platforms[source] = {
                    "configured": bool(value.get("configured")),
                    "ok": bool(value.get("configured")) and not value.get("error"),
                    "count": len(items),
                    "cached": bool(value.get("cached")),
                    "message": value.get("message") or value.get("error") or ("Connected" if value.get("configured") else "Not configured"),
                    "categories_scanned": value.get("categories_scanned"),
                }
            except Exception as exc:  # a broken platform must not hide the others
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
        int(item.get("viewers") or 0),
        str(item.get("started_at") or item.get("published") or ""),
    ), reverse=True)
    configured_count = sum(1 for item in platforms.values() if item["configured"])
    return {
        "mode": "live_now",
        "query": clean_query,
        "items": merged[:max_results],
        "count": len(merged),
        "platforms": platforms,
        "configured_sources": configured_count,
        "scanned_at": time.time(),
        "refresh_policy": {
            "youtube_minutes": SOURCE_TTLS["YouTube"] // 60,
            "other_platforms_minutes": SOURCE_TTLS["Twitch"] // 60,
        },
        "note": "Platform APIs confirm that each channel is live. APEX filters for motorsport relevance, but the actual race feed and access price should still be checked on the destination platform.",
    }
