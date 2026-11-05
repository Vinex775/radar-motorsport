"""Load a curated registry of events checked against official schedules.

This is an ingestion collector, not a generic web scraper. Official series use
incompatible pages/APIs, so each entry is stored with its source URL and check
context. Future page-specific/API collectors can feed the same event schema.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_FILE = ROOT / "data" / "official_schedule.json"


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


def _valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def fetch_official_schedule() -> list[dict[str, Any]]:
    """Return validated curated event records in APEX's common DB schema."""
    try:
        payload = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read official schedule registry: {exc}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise ValueError("Official schedule registry must contain an events list.")

    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(payload["events"]):
        if not isinstance(raw, dict):
            continue
        event = dict(raw)
        external_id = str(event.get("external_id") or "").strip()
        name = str(event.get("name") or "").strip()
        source_url = str(event.get("source_url") or "").strip()
        start_value = str(event.get("start") or "").strip()
        end_value = str(event.get("end") or "").strip() or None
        start = _parse_datetime(start_value)
        end = _parse_datetime(end_value)

        if not external_id or not name or not start or not source_url or not _valid_http_url(source_url):
            raise ValueError(f"Invalid official schedule record at index {index}: id, name, start and valid source_url are required.")
        if external_id in seen_ids:
            raise ValueError(f"Duplicate official schedule external_id: {external_id}")
        if end_value and (not end or end < start):
            raise ValueError(f"Invalid end time for official schedule record: {external_id}")
        if event.get("confidence") not in {"official", "regional"}:
            raise ValueError(f"Official schedule record must have official/regional confidence: {external_id}")
        if event.get("access", "unknown") not in {"free", "subscription", "ppv", "unknown"}:
            raise ValueError(f"Invalid access value for official schedule record: {external_id}")

        event.setdefault("series", "Motorsport")
        event.setdefault("category", "Other")
        event.setdefault("kind", "Event")
        event.setdefault("platform", "Official event schedule — broadcast TBC")
        event.setdefault("access", "unknown")
        event.setdefault("region", "Global")
        event.setdefault("source_name", "Official schedule registry")
        event.setdefault("watch_url", None)
        event.setdefault("stream_url", None)
        results.append(event)
        seen_ids.add(external_id)

    return results
