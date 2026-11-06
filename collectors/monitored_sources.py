"""Validated registry of permanent motorsport sources monitored by APEX.

Source records outlive individual seasons. A source may provide an official
calendar, future news, scheduled YouTube broadcasts, or a watch destination.
Those roles are intentionally kept separate.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MONITORED_SOURCES_FILE = ROOT / "data" / "monitored_sources.json"
ALLOWED_CONFIDENCE = {"official", "regional", "official_partner"}


def _valid_url(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def load_monitored_sources() -> list[dict[str, Any]]:
    """Load active sources, ignoring malformed or unverified registry rows."""
    try:
        payload = json.loads(MONITORED_SOURCES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        return []

    valid: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in payload["sources"]:
        if not isinstance(raw, dict):
            continue
        source = dict(raw)
        source_id = str(source.get("id") or "").strip()
        name = str(source.get("name") or "").strip()
        if not source_id or source_id in seen or not name:
            continue
        if source.get("confidence") not in ALLOWED_CONFIDENCE:
            continue
        if not any(_valid_url(source.get(key)) for key in ("official_url", "calendar_url", "news_url", "watch_url", "channel_url")):
            continue
        monitoring = source.get("monitoring")
        if not isinstance(monitoring, dict):
            continue
        # Watch-only partners may still live in this registry for clean
        # attribution, but do not create background requests unless enabled.
        source["monitoring"] = monitoring
        channel = source.get("youtube_channel")
        if not isinstance(channel, dict):
            source["youtube_channel"] = None
        elif not (str(channel.get("channel_id") or "").strip() or str(channel.get("handle") or "").strip()):
            source["youtube_channel"] = None
        seen.add(source_id)
        valid.append(source)
    return valid


def get_youtube_sources() -> list[dict[str, Any]]:
    """Return only verified, explicitly enabled official YouTube channels."""
    return [
        source for source in load_monitored_sources()
        if source.get("confidence") == "official"
        and source.get("monitoring", {}).get("youtube_upcoming") is True
        and isinstance(source.get("youtube_channel"), dict)
    ]


def get_discovery_sources() -> list[dict[str, Any]]:
    """Return official source records with a targeted future-news query."""
    return [
        source for source in load_monitored_sources()
        if source.get("monitoring", {}).get("discovery") is True
        and str(source.get("discovery_query") or "").strip()
    ]
