"""Convert future announcements from monitored official YouTube channels into leads."""
from __future__ import annotations

import hashlib
from typing import Any

from collectors.discovery import (
    classify_access,
    detect_series,
    is_reaction_or_commentary,
    is_upcoming_discovery,
)


def build_channel_discovery_leads(channel_items: list[dict], details: dict[str, dict], limit: int = 100) -> list[dict[str, Any]]:
    """Create future-focused editorial leads from recent videos on trusted channels.

    A registered channel is trusted as a motorsport publisher, but its videos
    are still required to contain a future signal (e.g. 2027, calendar, entries,
    next season). Recaps, replays and reactions remain excluded.
    """
    leads: dict[str, dict[str, Any]] = {}
    for item in channel_items:
        video_id = str((item.get("id") or {}).get("videoId") or "").strip()
        if not video_id:
            continue
        detail = details.get(video_id) or {}
        snippet = detail.get("snippet") or {}
        feed_snippet = item.get("snippet") or {}
        title = str(snippet.get("title") or feed_snippet.get("title") or "").strip()
        description = str(snippet.get("description") or "").strip()
        published = snippet.get("publishedAt") or feed_snippet.get("publishedAt")
        channel_name = str(
            snippet.get("channelTitle")
            or feed_snippet.get("monitoringSourceName")
            or feed_snippet.get("channelTitle")
            or "Official motorsport channel"
        )
        source_series = feed_snippet.get("monitoringSeries") or []
        if isinstance(source_series, str):
            source_series = [source_series]
        source_series = [str(value).strip() for value in source_series if str(value).strip()]
        future_context = f"{title} {description} {' '.join(source_series)}"
        if not title or is_reaction_or_commentary(title, description):
            continue
        if not is_upcoming_discovery(title, future_context, published):
            continue

        url = f"https://www.youtube.com/watch?v={video_id}"
        lead_id = hashlib.sha256(url.encode("utf-8")).hexdigest()[:18]
        series = source_series[0] if source_series else detect_series(future_context)
        summary = description[:500] or f"Future announcement published by the official {channel_name} channel."
        leads[url] = {
            "id": lead_id,
            "title": title,
            "summary": summary,
            "url": url,
            "published": published,
            "source_name": f"{channel_name} · monitored official channel",
            "series": series,
            "platform": "YouTube",
            "access": classify_access(description),
            "lead_status": "upcoming_lead",
            "is_verified_live": False,
            "note": (
                f"Future announcement identified in the monitored official channel {channel_name}. "
                "Check the original video and organizer page for confirmed dates, sessions and broadcast details. "
                "This is not evidence that a stream is live."
            ),
        }

    ordered = sorted(leads.values(), key=lambda lead: lead.get("published") or "", reverse=True)
    return ordered[:max(1, min(int(limit), 200))]
