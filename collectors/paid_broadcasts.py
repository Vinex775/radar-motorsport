"""Official same-day motorsport sessions and regional watch options for APEX.

This module joins APEX's source-checked event registry to its official watch
 directory. A schedule window is deliberately never labelled as a verified
live stream; only the platform collectors can make that assertion.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone, tzinfo
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
WATCH_SOURCES_FILE = ROOT / "data" / "watch_sources.json"
MONITORED_SOURCES_FILE = ROOT / "data" / "monitored_sources.json"
ACCESS_VALUES = {"free", "subscription", "ppv", "unknown"}
ACCESS_ORDER = {"free": 0, "subscription": 1, "ppv": 2, "unknown": 3}

# Explicit aliases keep similarly named championships and services separate.
SERIES_GROUPS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("f1", re.compile(r"\b(?:formula\s*1|f1)\b", re.I)),
    ("formula-e", re.compile(r"\bformula\s*e\b", re.I)),
    ("f4-brasil", re.compile(r"\bf4\s*(?:brasil|brazil)\b", re.I)),
    ("wec", re.compile(r"\b(?:fia\s*wec|wec|world endurance championship)\b", re.I)),
    ("motogp", re.compile(r"\b(?:motogp|moto2|moto3)\b", re.I)),
    ("worldsbk", re.compile(r"\b(?:worldsbk|worldssp|worldspb)\b", re.I)),
    ("supercars", re.compile(r"\b(?:supercars championship|supercars|sandown 500)\b", re.I)),
    ("nascar", re.compile(r"\bnascar\b", re.I)),
    ("world-of-outlaws", re.compile(r"\b(?:world of outlaws|super dirtcar|dirtvision)\b", re.I)),
    ("powri", re.compile(r"\b(?:powri|heartland late model|410 outlaw sprint)\b", re.I)),
    ("porsche-cup", re.compile(r"\b(?:porsche cup|carrera cup|sprint challenge|porsche trophy)\b", re.I)),
    ("yamaha-blucru", re.compile(r"\b(?:blu\s*cru|yamaha r3|yamaha r15)\b", re.I)),
    ("nhra", re.compile(r"\bnhra\b", re.I)),
    ("smx", re.compile(r"\b(?:smx|supercross|pro motocross)\b", re.I)),
    ("indycar", re.compile(r"\b(?:indycar|indy nxt|ntt indycar)\b", re.I)),
    ("dtm", re.compile(r"\bdtm\b", re.I)),
    ("adac-gt", re.compile(r"\b(?:adac gt|gt masters|gt4 germany)\b", re.I)),
    ("gt-world", re.compile(r"\b(?:gt world|gt world challenge|sro america)\b", re.I)),
    ("rally-tv", re.compile(r"\b(?:wrc|erc|world rally championship|rally\.tv)\b", re.I)),
    ("fia-karting", re.compile(r"\bfia karting\b", re.I)),
    ("imsa", re.compile(r"\bimsa\b", re.I)),
    ("speedway", re.compile(r"\b(?:fim speedway|speedway grand prix)\b", re.I)),
)


def _valid_url(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = urlparse(value.strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _series_group(value: str) -> str | None:
    for key, pattern in SERIES_GROUPS:
        if pattern.search(value or ""):
            return key
    return None


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _source_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    watch_sources = _read_json(WATCH_SOURCES_FILE, [])
    if isinstance(watch_sources, list):
        for item in watch_sources:
            if isinstance(item, dict) and item.get("confidence") in {"official", "regional"}:
                rows.append({
                    "id": item.get("id"),
                    "name": item.get("platform") or item.get("series") or "Official watch source",
                    "series": item.get("series") or "",
                    "region": item.get("region") or "Global",
                    "platform": item.get("platform") or "Official watch source",
                    "access": item.get("access", "unknown"),
                    "url": item.get("url"),
                    "note": item.get("note") or "Official watch guide; check event, session and regional availability.",
                    "confidence": item.get("confidence"),
                })

    monitored = _read_json(MONITORED_SOURCES_FILE, {})
    monitored_rows = monitored.get("sources", []) if isinstance(monitored, dict) else []
    if isinstance(monitored_rows, list):
        for item in monitored_rows:
            if not isinstance(item, dict) or item.get("confidence") not in {"official", "official_partner"}:
                continue
            url = item.get("watch_url")
            if not _valid_url(url):
                continue
            series = item.get("series") or []
            if isinstance(series, list):
                series = " / ".join(str(value) for value in series)
            rows.append({
                "id": item.get("id"),
                "name": item.get("name") or "Official watch destination",
                "series": series,
                "region": item.get("region") or "Global",
                "platform": item.get("name") or "Official watch destination",
                "access": item.get("access", "unknown"),
                "url": url,
                "note": item.get("notes") or "Official destination. Check the event, session and regional availability.",
                "confidence": item.get("confidence"),
            })
    return rows


def resolve_watch_options(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Return official watch destinations that match an event's series."""
    event_text = f"{event.get('series') or ''} {event.get('name') or ''}"
    group = _series_group(event_text)
    options: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    if group:
        for source in _source_rows():
            source_text = f"{source.get('series') or ''} {source.get('name') or ''} {source.get('platform') or ''}"
            if _series_group(source_text) != group or not _valid_url(source.get("url")):
                continue
            access = source.get("access") if source.get("access") in ACCESS_VALUES else "unknown"
            platform = str(source.get("platform") or source.get("name") or "Official watch source")[:160]
            url = str(source["url"]).strip()
            key = (url.rstrip("/"), platform.casefold(), access)
            if key in seen:
                continue
            seen.add(key)
            options.append({
                "id": str(source.get("id") or f"{group}:{len(options)}"),
                "platform": platform,
                "access": access,
                "url": url,
                "region": str(source.get("region") or "Global")[:120],
                "confidence": source.get("confidence") or "official",
                "note": str(source.get("note") or "Check event and territory availability.")[:300],
                "link_type": "watch",
            })

    # Preserve a direct stream URL or the event's official event/watch page.
    direct_url = event.get("stream_url")
    watch_url = event.get("watch_url")
    chosen_url = direct_url if _valid_url(direct_url) else watch_url
    if _valid_url(chosen_url):
        access = event.get("access") if event.get("access") in ACCESS_VALUES else "unknown"
        url = str(chosen_url).strip()
        duplicate = next((option for option in options if option["url"].rstrip("/") == url.rstrip("/")), None)
        if duplicate:
            # An event record can know the exact access tier even when a general
            # partner directory only says "unknown" (for example, DIRTVision).
            if access != "unknown":
                duplicate["access"] = access
            if _valid_url(direct_url) and event.get("platform"):
                duplicate["platform"] = str(event.get("platform"))[:160]
            if event.get("region") and duplicate.get("region") == "Global":
                duplicate["region"] = str(event.get("region"))[:120]
        else:
            options.append({
                "id": f"event:{event.get('external_id') or 'official'}",
                "platform": (
                    str(event.get("platform") or "Official event / watch page")[:160]
                    if _valid_url(direct_url)
                    else "Official event / coverage page"
                ),
                "access": access,
                "url": url,
                "region": str(event.get("region") or "Global")[:120],
                "confidence": event.get("confidence") or "official",
                "note": "Official event information. Confirm the actual live feed, session, price and territory at the destination.",
                "link_type": "stream" if _valid_url(direct_url) else "event_info",
            })

    options.sort(key=lambda item: (ACCESS_ORDER.get(item.get("access", "unknown"), 3), item.get("platform", "").casefold()))
    return options


def enrich_event_with_watch_options(event: dict[str, Any]) -> dict[str, Any]:
    """Copy a Schedule event and attach matching official watch choices."""
    result = dict(event)
    result["watch_options"] = resolve_watch_options(result)
    return result


def collect_today_paid_options(local_now: datetime | None = None) -> list[dict[str, Any]]:
    """Create Live Now & Today rows from source-checked official sessions.

    Rows cover every official session/event overlapping the browser's local
    calendar day. Their status describes the published timetable, not an
    observed video stream. Both curated registry and already-saved DTM/manual
    events are considered; YouTube rows are handled by the existing collector.
    """
    if local_now is None:
        local_now = datetime.now().astimezone()
    elif local_now.tzinfo is None:
        local_now = local_now.astimezone()
    local_today = local_now.date()
    now_utc = local_now.astimezone(timezone.utc)

    candidates: list[dict[str, Any]] = []
    try:
        from collectors.official_schedule import fetch_official_schedule
        candidates.extend(fetch_official_schedule())
    except Exception:
        # A bad registry must not take down the live-platform scan.
        pass

    try:
        import db
        for stored in db.get_events():
            if stored.get("source") in {"youtube_scheduled", "official_schedule"}:
                continue
            candidates.append(stored)
    except Exception:
        pass

    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in candidates:
        event = dict(raw)
        external_id = str(event.get("external_id") or "").strip()
        if not external_id:
            continue
        source = str(event.get("source") or "official_schedule")
        key = (source, external_id)
        if key in seen:
            continue
        seen.add(key)

        start = _parse_dt(event.get("start_utc") or event.get("start"))
        end = _parse_dt(event.get("end_utc") or event.get("end"))
        if not start:
            continue
        local_start = start.astimezone(local_now.tzinfo)
        local_end = end.astimezone(local_now.tzinfo) if end else None
        overlaps_today = local_start.date() == local_today or bool(local_end and local_start.date() <= local_today <= local_end.date())
        if not overlaps_today:
            continue

        kind = str(event.get("kind") or "").casefold()
        date_only = "date range only" in kind or "times tbc" in kind or "time tbc" in kind
        if date_only:
            status = "date_only_today"
        elif start > now_utc:
            status = "scheduled_today"
        elif end and end > now_utc:
            status = "schedule_window"
        elif end and end <= now_utc:
            status = "ended_today"
        else:
            status = "start_time_passed"

        options = resolve_watch_options(event)
        access = event.get("access") if event.get("access") in ACCESS_VALUES else "unknown"
        platform_names = [str(option.get("platform") or "") for option in options if option.get("platform")]
        platform = " / ".join(dict.fromkeys(platform_names)) or str(event.get("platform") or "Official event schedule")
        first_url = next((option.get("url") for option in options if _valid_url(option.get("url"))), None)
        item_url = first_url or event.get("watch_url") or event.get("source_url")
        title = str(event.get("name") or "Official motorsport session")
        series = str(event.get("series") or "Motorsport")
        results.append({
            "id": f"official-schedule:{external_id}",
            "external_id": external_id,
            "title": title,
            "description": str(event.get("kind") or "Officially scheduled motorsport session"),
            "channel": series,
            "series": series,
            "scheduled_start_at": start.isoformat(),
            "scheduled_end_at": end.isoformat() if end else None,
            "url": item_url,
            "platform": platform[:260],
            "category": str(event.get("category") or "Motorsport"),
            "access": access,
            "watch_options": options,
            "status": status,
            "is_verified_live": False,
            "source": "official_schedule" if source != "manual" else "manual",
            "verification": "APEX source-checked official schedule registry / local event record; not provider-verified live",
            "note": (
                "Official schedule lists this event for today, but does not confirm that a video stream is currently live. Open a listed destination and verify session, price and regional access."
                if options else
                "Official schedule lists this event for today. A live video or accessible broadcaster was not confirmed; consult the official event information."
            ),
            "region": str(event.get("region") or "Global"),
            "kind": str(event.get("kind") or "Event"),
        })

    priority = {"schedule_window": 0, "scheduled_today": 1, "date_only_today": 2, "start_time_passed": 3, "ended_today": 4}
    results.sort(key=lambda item: (priority.get(item.get("status"), 5), item.get("scheduled_start_at") or "", item.get("title") or ""))
    return results
