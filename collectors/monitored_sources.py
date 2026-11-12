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
MONITORED_SOURCES_ADDITIONS_FILE = ROOT / "data" / "monitored_sources_additions.json"
ALLOWED_CONFIDENCE = {"official", "regional", "official_partner"}


def _valid_url(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def load_monitored_sources() -> list[dict[str, Any]]:
    """Load the main registry plus optional, additive source records.

    The additive file lets APEX expand its source coverage without replacing
    or rewriting the user's existing monitored_sources.json.
    """
    valid: list[dict[str, Any]] = []
    seen: set[str] = set()

    for registry_file in (MONITORED_SOURCES_FILE, MONITORED_SOURCES_ADDITIONS_FILE):
        try:
            payload = json.loads(registry_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
            continue

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
    """Return explicitly enabled official or vetted regional YouTube channels.

    Regional broadcasters are allowed only when they have their own
    validated source record and youtube_upcoming is explicitly enabled.
    Official broadcast partners remain excluded unless represented as a
    regional broadcaster record with this opt-in.
    """
    return [
        source for source in load_monitored_sources()
        if source.get("confidence") in {"official", "regional"}
        and source.get("monitoring", {}).get("youtube_upcoming") is True
        and isinstance(source.get("youtube_channel"), dict)
    ]


def get_discovery_sources() -> list[dict[str, Any]]:
    """Return registered source records with a targeted future-news query."""
    return [
        source for source in load_monitored_sources()
        if source.get("monitoring", {}).get("discovery") is True
        and str(source.get("discovery_query") or "").strip()
    ]
