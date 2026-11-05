from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from collectors.calendario_dtm import fetch_dtm_events as fetch_dtm_events_dtm
from collectors.discovery import discover_broadcast_leads
import db

ROOT = Path(__file__).resolve().parent
WATCH_SOURCES_FILE = ROOT / "data" / "watch_sources.json"
SEARCH_PRESETS_FILE = ROOT / "data" / "search_presets.json"

# These are official organizer, championship, or broadcaster destinations.
# Regional guides are retained when the page itself is published by an
# official rights-holder or organizer. Community-only links are not shown.
OFFICIAL_WATCH_ADDITIONS: list[dict[str, Any]] = [
    {
        "id": "dirtvision-world-of-outlaws",
        "series": "World of Outlaws / Super DIRTcar / sprint cars",
        "region": "United States — international access varies",
        "platform": "DIRTVision",
        "access": "subscription",
        "url": "https://www.dirtvision.com/",
        "official_info": "https://superdirtcarseries.com/schedule/",
        "note": "Official streaming destination for World of Outlaws and related dirt-track events. Check the event page for live coverage and subscription terms.",
        "confidence": "official",
        "last_checked": "2026-11-05"
    },
    {
        "id": "imsa-domestic-coverage",
        "series": "IMSA WeatherTech SportsCar Championship",
        "region": "United States — online video restricted by territory",
        "platform": "NBC / Peacock Premium / NBC Sports",
        "access": "subscription",
        "url": "https://www.imsa.com/how-to-watch/domestic-coverage",
        "official_info": "https://www.imsa.com/how-to-watch/domestic-coverage",
        "note": "Official IMSA domestic guide. Lists NBC, NBC Sports and Peacock Premium; NBC Sports digital access requires an eligible TV-provider login. Online video is US-only.",
        "confidence": "official",
        "last_checked": "2026-11-05"
    },
    {
        "id": "karting-sm-finland",
        "series": "Karting SM — Finnish Karting Championship",
        "region": "Finland",
        "platform": "Karting SM Live / FlyingFinn.tv",
        "access": "unknown",
        "url": "https://kartingsm.fi/live",
        "official_info": "https://kartingsm.fi/live",
        "note": "Official championship live page with broadcast and timing links. Check each round for the actual stream, session and access conditions.",
        "confidence": "official",
        "last_checked": "2026-11-05"
    }
]


def _is_official_source(source: dict[str, Any]) -> bool:
    if source.get("confidence") not in {"official", "regional"}:
        return False
    url = str(source.get("url") or "")
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def load_watch_sources() -> list[dict[str, Any]]:
    try:
        loaded = json.loads(WATCH_SOURCES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        loaded = []
    if not isinstance(loaded, list):
        loaded = []
    sources = [item for item in loaded if isinstance(item, dict) and _is_official_source(item)]
    known_ids = {item.get("id") for item in sources}
    for item in OFFICIAL_WATCH_ADDITIONS:
        if item["id"] not in known_ids:
            sources.append(dict(item))
    return sources


def load_search_presets() -> list[dict[str, Any]]:
    try:
        return json.loads(SEARCH_PRESETS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _run_dtm() -> tuple[list[dict], str | None]:
    try:
        return fetch_dtm_events_dtm(), None
    except Exception as exc:  # each collector is isolated so it cannot take down the radar
        return [], f"DTM: {type(exc).__name__}: {exc}"


def _run_discovery() -> tuple[list[dict], str | None]:
    try:
        return discover_broadcast_leads(), None
    except Exception as exc:
        return [], f"News discovery: {type(exc).__name__}: {exc}"


def refresh_all() -> dict[str, Any]:
    """Refresh collectors in parallel and preserve stored data when a source fails."""
    errors: list[str] = []
    event_count = 0
    discovery_count = 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_run_dtm), pool.submit(_run_discovery)]
        for future in as_completed(futures):
            records, error = future.result()
            if error:
                errors.append(error)
                continue
            if records and "external_id" in records[0]:
                for event in records:
                    db.upsert_event(event, "dtm")
                event_count += len(records)
            else:
                db.save_discoveries(records)
                discovery_count += len(records)
    refreshed = datetime.now(timezone.utc).isoformat()
    db.set_setting("last_refresh", refreshed)
    return {
        "ok": not errors,
        "events_updated": event_count,
        "discoveries_updated": discovery_count,
        "errors": errors,
        "refreshed_at": refreshed,
    }


def event_status(event: dict[str, Any], now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    start = _parse_dt(event.get("start_utc"))
    end = _parse_dt(event.get("end_utc"))
    if not start:
        return "unknown"
    if start > now:
        return "upcoming"
    if end and end >= now:
        return "live"  # Scheduled session window only; never proof of a video stream.
    if not end:
        return "unknown"
    return "past"


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def dashboard_data() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    # Reclassify stored leads against the current date before presenting them.
    db.purge_irrelevant_discoveries()

    all_events = db.get_events()
    for event in all_events:
        event["status"] = event_status(event, now)

    # Schedule & Events is deliberately future-only. A scheduled window that
    # has already started belongs to neither this list nor Live Now; Live Now
    # is populated exclusively by the streaming-platform APIs.
    upcoming_events = [event for event in all_events if event["status"] == "upcoming"]
    upcoming_events.sort(key=lambda event: event.get("start_utc") or "")

    stored_discoveries = db.get_discoveries()
    discoveries = [item for item in stored_discoveries if item.get("lead_status") == "upcoming_lead"]
    return {
        "events": upcoming_events,
        "discoveries": discoveries,
        "sources": load_watch_sources(),
        "search_presets": load_search_presets(),
        "stats": {
            "live": 0,
            "upcoming": len(upcoming_events),
            "leads": len(discoveries),
        },
        "last_refresh": db.get_setting("last_refresh"),
        "now": now.isoformat(),
    }
