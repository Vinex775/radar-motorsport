"""Coleta o calendário público da DTM.

A API não é uma API pública documentada; por isso o coletor falha de forma
segura e nunca impede que os demais módulos do radar funcionem.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://api.dtm.com/data"
HEADERS = {"User-Agent": "MotorsportRadar/1.0 (personal motorsport schedule aggregator)"}


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
        raise OSError(f"Falha ao consultar a API da DTM: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("A API da DTM retornou um formato inesperado.")
    return payload


def buscar_eventos() -> list[dict[str, Any]]:
    """Retorna sessões futuras/atuais da DTM no formato padronizado do radar."""
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
        if not start or (end and end < now):
            continue
        candidates.append((start, event))

    candidates.sort(key=lambda item: item[0])
    if not candidates:
        return []

    # Coleta a programação das próximas etapas que a API disponibilizar.
    results: list[dict[str, Any]] = []
    for _, event in candidates[:3]:
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
            if not start:
                continue
            if end and end < now:
                continue
            label = session.get("label") or "Sessão"
            headline = session.get("headline") or details.get("name") or "DTM"
            results.append({
                "external_id": f"dtm:{slug}:{session.get('id') or start.isoformat()}:{label}",
                "name": headline,
                "series": "DTM",
                "category": "Turismo / GT",
                "kind": label,
                "start": start.isoformat(),
                "end": end.isoformat() if end else None,
                "platform": "Ver canais oficiais",
                "access": "unknown",
                "stream_url": None,
                "watch_url": "https://www.dtm.com/live/live-on-tv",
                "region": "Global — disponibilidade varia por país",
                "confidence": "regional",
                "source_name": "DTM oficial",
                "source_url": "https://www.dtm.com/live/live-on-tv",
            })
            added_sessions += 1

        # Caso o cronograma de sessões ainda não esteja publicado.
        if not added_sessions:
            start = _parse_datetime(details.get("startTime") or event.get("startTime"))
            end = _parse_datetime(details.get("endTime") or event.get("endTime"))
            if start:
                results.append({
                    "external_id": f"dtm:{slug}:weekend",
                    "name": details.get("name") or event.get("name") or "Etapa DTM",
                    "series": "DTM",
                    "category": "Turismo / GT",
                    "kind": "Fim de semana de corrida",
                    "start": start.isoformat(),
                    "end": end.isoformat() if end else None,
                    "platform": "Ver canais oficiais",
                    "access": "unknown",
                    "stream_url": None,
                    "watch_url": "https://www.dtm.com/live/live-on-tv",
                    "region": "Global — disponibilidade varia por país",
                    "confidence": "regional",
                    "source_name": "DTM oficial",
                    "source_url": "https://www.dtm.com/live/live-on-tv",
                })
    return results
