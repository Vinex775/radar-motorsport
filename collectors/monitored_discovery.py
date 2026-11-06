"""Targeted future-news searches for APEX's permanent official-source registry."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree

from collectors.discovery import FUTURE_NEWS_TERMS, _fetch_query, _parse_feed
from collectors.monitored_sources import get_discovery_sources


def discover_monitored_source_leads(limit: int = 100) -> list[dict]:
    """Search official-source domains for future calendars and announcements.

    Google News is used as an index, not as proof. The standard APEX future-lead
    and motorsport filters run again, and every item keeps a reference to the
    source registry entry that caused the targeted search.
    """
    sources = get_discovery_sources()
    if not sources:
        return []

    merged: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(8, len(sources))) as pool:
        futures = {
            pool.submit(_fetch_query, f'({source["discovery_query"]}) {FUTURE_NEWS_TERMS}'): source
            for source in sources
        }
        for future in as_completed(futures):
            source = futures[future]
            try:
                payload = future.result()
                items = _parse_feed(payload, limit=max(10, min(limit, 40)))
            except (HTTPError, URLError, TimeoutError, OSError, ElementTree.ParseError):
                continue
            for item in items:
                item["monitoring_source_id"] = source["id"]
                item["monitoring_source_name"] = source["name"]
                publication = str(item.get("source_name") or "Official publication")
                item["source_name"] = f"{publication} · monitored: {source['name']}"[:180]
                if item.get("lead_status") == "upcoming_lead":
                    item["note"] = (
                        f"Found through the permanent APEX source monitor for {source['name']}. "
                        "This is a future motorsport lead, not confirmation of a live broadcast; "
                        "verify the date and session on the original organizer page."
                    )
                merged[item["url"]] = item

    ordered = sorted(merged.values(), key=lambda item: item.get("published") or "", reverse=True)
    return ordered[:max(1, min(int(limit), 150))]
