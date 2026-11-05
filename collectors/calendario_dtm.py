"""Collect the official DTM schedule.

The API is not publicly documented, so this collector fails safely and
never prevents other radar modules from working.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://api.dtm.com/data"
HEADERS = {"User-Agent": "APEX-Motorsport-Radar/1.5.0 (local motorsport schedule aggregator)"}


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _get(params: dict[str, Any]) -> dict[str, Any]:
    url = API + "?" + urlencode(params)
    request = Request(url, headers=HEADERS)
    try:
        with urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise OSError(f"Failed to query the DTM API: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("The DTM API returned an unexpected format.")
    return payload


def _is_future_or_active(start: datetime | None, end: datetime | None, now: datetime) -> bool:
    """Reject sessions/weekends that have ended, including entries with no end time."""
    if not start:
        return False
    if start > now:
        return True
    return bool(end and end >= now)


def fetch_dtm_events() -> list[dict[str, Any]]:
    """Return current/future DTM sessions in the APEX schedule format."""
    payload = _get({"query": "eventsRacetrack"})
    now = datetime.now(timezone.utc)
    candidates = []

    for event in payload.get("events", []) or []:
        series = event.get("raceSeries") or []
        if isinstance(series, str):
            series = [series]
        if not any("DTM" in str(item).upper() for item in series):
            continue
        start = _parse_datetime(event.get("startTime"))
        end = _parse_datetime(event.get("endTime"))
        if not _is_future_or_active(start, end, now):
            continue
        candidates.append((start, event))

    candidates.sort(key=lambda item: item[0])
    if not candidates:
        return []

    results: list[dict[str, Any]] = []
    for _, event in candidates[:8]:
        slug = event.get("slug")
        if not slug:
            continue
        try:
            detail_payload = _get({"query": "eventDetails", "slug": slug})
            details = (detail_payload.get("events") or [])[0]
        except (OSError, ValueError, IndexError, KeyError):
            details = event

        timetable = details.get("timetable") or []
        added_sessions = 0
        for session in timetable:
            series_name = str(session.get("raceSeries") or "")
            if "DTM" not in series_name.upper():
                continue
            start = _parse_datetime(session.get("start"))
            end = _parse_datetime(session.get("end"))
            if not _is_future_or_active(start, end, now):
                continue

            label = session.get("label") or "Session"
            headline = session.get("headline") or details.get("name") or "DTM"
            results.append({
                "external_id": f"dtm:{slug}:{session.get('id') or start.isoformat()}:{label}",
                "name": headline,
                "series": "DTM",
                "category": "Touring Cars / GT",
                "kind": label,
                "start": start.isoformat(),
                "end": end.isoformat() if end else None,
                "platform": "See official broadcasters",
                "access": "unknown",
                "stream_url": None,
                "watch_url": "https://www.dtm.com/live/live-on-tv",
                "region": "Global — availability varies by country",
                "confidence": "regional",
                "source_name": "DTM official",
                "source_url": "https://www.dtm.com/live/live-on-tv",
            })
            added_sessions += 1

        # If the session timetable has not been published, retain the weekend
        # range. The UI displays a date range and deliberately suppresses the
        # API's evening placeholder time for a full race weekend.
        if not added_sessions:
            start = _parse_datetime(details.get("startTime") or event.get("startTime"))
            end = _parse_datetime(details.get("endTime") or event.get("endTime"))
            if _is_future_or_active(start, end, now):
                results.append({
                    "external_id": f"dtm:{slug}:weekend",
                    "name": details.get("name") or event.get("name") or "DTM round",
                    "series": "DTM",
                    "category": "Touring Cars / GT",
                    "kind": "Race weekend",
                    "start": start.isoformat(),
                    "end": end.isoformat() if end else None,
                    "platform": "See official broadcasters",
                    "access": "unknown",
                    "stream_url": None,
                    "watch_url": "https://www.dtm.com/live/live-on-tv",
                    "region": "Global — availability varies by country",
                    "confidence": "regional",
                    "source_name": "DTM official",
                    "source_url": "https://www.dtm.com/live/live-on-tv",
                })
    return results
