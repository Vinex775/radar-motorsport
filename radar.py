from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collectors.calendario_dtm import buscar_eventos as buscar_eventos_dtm
from collectors.discovery import buscar_pistas
import db

ROOT = Path(__file__).resolve().parent
WATCH_SOURCES_FILE = ROOT / "data" / "watch_sources.json"
SEARCH_PRESETS_FILE = ROOT / "data" / "search_presets.json"


def load_watch_sources() -> list[dict[str, Any]]:
    try:
        return json.loads(WATCH_SOURCES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def load_search_presets() -> list[dict[str, Any]]:
    try:
        return json.loads(SEARCH_PRESETS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _run_dtm() -> tuple[list[dict], str | None]:
    try:
        return buscar_eventos_dtm(), None
    except Exception as exc:  # cada coletor é isolado para não derrubar o radar
        return [], f"DTM: {type(exc).__name__}: {exc}"


def _run_discovery() -> tuple[list[dict], str | None]:
    try:
        return buscar_pistas(), None
    except Exception as exc:
        return [], f"Busca de notícias: {type(exc).__name__}: {exc}"


def refresh_all() -> dict[str, Any]:
    """Atualiza os coletores em paralelo e conserva os dados já salvos em falhas."""
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
        return "live"
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
    # Limpa também os falsos positivos já salvos por versões anteriores.
    db.purge_irrelevant_discoveries()
    events = db.get_events()
    for event in events:
        event["status"] = event_status(event, now)
    events = [event for event in events if event["status"] != "past"]
    events.sort(key=lambda event: (event["status"] != "live", event.get("start_utc") or ""))
    live = sum(1 for event in events if event["status"] == "live")
    upcoming = sum(1 for event in events if event["status"] == "upcoming")
    return {
        "events": events,
        "discoveries": db.get_discoveries(),
        "sources": load_watch_sources(),
        "search_presets": load_search_presets(),
        "stats": {"live": live, "upcoming": upcoming, "leads": len(db.get_discoveries())},
        "last_refresh": db.get_setting("last_refresh"),
        "now": now.isoformat(),
    }
