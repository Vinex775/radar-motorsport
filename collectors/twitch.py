"""Discover active motorsport streams through Twitch Helix.

Requires a Twitch developer application. Credentials are read from environment
variables (or the local .env file loaded by config.py).
"""
from __future__ import annotations

import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from collectors.discovery import is_motorsport_result, is_reaction_or_commentary

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
API_BASE = "https://api.twitch.tv/helix"
CATEGORY_QUERIES = (
    "motorsport", "racing", "karting", "rally", "motocross", "speedway",
    "drift", "drag racing", "hill climb", "autosuunnistus", "folkrace",
    "rallisprint", "stock car", "tractor pulling", "iRacing", "Assetto Corsa",
    "Gran Turismo", "Forza Motorsport", "Automobilista", "rFactor",
)
SIM_RACING_RE = re.compile(
    r"\b(?:sim racing|simracing|iracing|assetto corsa|gran turismo|forza motorsport|"
    r"automobilista|rfactor(?:\s?2)?|race room|raceroom)\b", re.IGNORECASE
)

_TOKEN: str | None = None
_TOKEN_EXPIRES = 0.0
_TOKEN_CLIENT_ID: str | None = None
_CATEGORY_CACHE: dict[str, tuple[float, list[dict]]] = {}


def _request_json(url: str, headers: dict | None = None, data: bytes | None = None) -> dict:
    request = Request(url, headers=headers or {}, data=data)
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("message") or ""
        except (ValueError, AttributeError):
            detail = ""
        raise RuntimeError(detail or f"Twitch API returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(f"Could not query Twitch: {exc}") from exc


def _credentials() -> tuple[str, str]:
    return os.environ.get("TWITCH_CLIENT_ID", "").strip(), os.environ.get("TWITCH_CLIENT_SECRET", "").strip()


def _app_token(client_id: str, client_secret: str) -> str:
    global _TOKEN, _TOKEN_EXPIRES, _TOKEN_CLIENT_ID
    if _TOKEN and _TOKEN_CLIENT_ID == client_id and time.monotonic() < _TOKEN_EXPIRES - 60:
        return _TOKEN
    body = urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }).encode("ascii")
    payload = _request_json(
        TOKEN_URL,
        {"Content-Type": "application/x-www-form-urlencoded"},
        body,
    )
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("Twitch did not return an app access token.")
    _TOKEN = token
    _TOKEN_CLIENT_ID = client_id
    _TOKEN_EXPIRES = time.monotonic() + int(payload.get("expires_in", 3600))
    return token


def _api_get(path: str, params: list[tuple[str, str]], client_id: str, token: str) -> dict:
    url = f"{API_BASE}{path}?{urlencode(params)}"
    return _request_json(url, {
        "Client-Id": client_id,
        "Authorization": f"Bearer {token}",
        "User-Agent": "APEX-Motorsport-Radar",
    })


CATEGORY_LABEL_RE = re.compile(
    r"^(?:rally|racing|auto racing|car racing|kart|karting|motorsport|motorsports|"
    r"motocross|speedway|drift|drag racing|hill ?climb|enduro|stock car|"
    r"short track racing|folkrace|rallisprint|autosuunnistus|tractor pulling)$",
    re.IGNORECASE,
)


def _motorsport_category(name: str) -> bool:
    # Some platform categories use a short standalone label (e.g. "Rally")
    # that is ambiguous in general news but valid as a Twitch game category.
    return bool(CATEGORY_LABEL_RE.fullmatch(name.strip())) or is_motorsport_result(name, "") or bool(SIM_RACING_RE.search(name))


def _find_categories(client_id: str, token: str) -> list[dict]:
    now = time.monotonic()
    cached = _CATEGORY_CACHE.get(client_id)
    if cached and cached[1] and now - cached[0] < 24 * 60 * 60:
        return cached[1]

    found: dict[str, dict] = {}
    for query in CATEGORY_QUERIES:
        payload = _api_get("/search/categories", [("query", query), ("first", "100")], client_id, token)
        for category in payload.get("data", []) or []:
            category_id = str(category.get("id") or "")
            name = str(category.get("name") or "")
            if category_id and name and _motorsport_category(name):
                found[category_id] = {"id": category_id, "name": name}
    categories = list(found.values())
    _CATEGORY_CACHE[client_id] = (now, categories)
    return categories


def search_live_streams(max_results: int = 300) -> dict:
    """Return currently active Twitch streams in motorsport and sim-racing categories."""
    client_id, client_secret = _credentials()
    if not client_id or not client_secret:
        return {
            "configured": False,
            "items": [],
            "source": "twitch",
            "message": "Set TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET to enable Twitch live discovery.",
        }

    token = _app_token(client_id, client_secret)
    categories = _find_categories(client_id, token)
    if not categories:
        return {"configured": True, "items": [], "source": "twitch", "categories_scanned": 0}

    params: list[tuple[str, str]] = [("first", "100")]
    params.extend(("game_id", item["id"]) for item in categories[:100])
    items: dict[str, dict] = {}
    cursor = None
    max_pages = max(1, min((int(max_results) + 99) // 100, 5))

    for _ in range(max_pages):
        page_params = list(params)
        if cursor:
            page_params.append(("after", cursor))
        payload = _api_get("/streams", page_params, client_id, token)
        for stream in payload.get("data", []) or []:
            stream_id = str(stream.get("id") or "")
            title = str(stream.get("title") or "")
            game = str(stream.get("game_name") or "")
            tags = " ".join(stream.get("tags") or [])
            if not stream_id or not (_motorsport_category(game) or is_motorsport_result(title, tags) or SIM_RACING_RE.search(title)):
                continue
            if is_reaction_or_commentary(title, tags):
                continue
            login = str(stream.get("user_login") or "")
            channel = str(stream.get("user_name") or login or "Twitch channel")
            items[stream_id] = {
                "id": f"twitch:{stream_id}",
                "title": title or game or "Live motorsport stream",
                "channel": channel,
                "category": game or "Motorsport",
                "platform": "Twitch",
                "url": f"https://www.twitch.tv/{login}" if login else "https://www.twitch.tv/",
                "thumbnail": str(stream.get("thumbnail_url") or "").replace("{width}", "320").replace("{height}", "180"),
                "started_at": stream.get("started_at"),
                "viewers": int(stream.get("viewer_count") or 0),
                "language": stream.get("language"),
                "access": "unknown",
                "status": "live_now",
                "is_verified_live": True,
                "verification": "Twitch Helix Get Streams",
                "note": "Twitch confirms that this channel is live. Open it to verify that it is showing a motorsport session rather than commentary or another related stream.",
            }
        cursor = (payload.get("pagination") or {}).get("cursor")
        if not cursor or len(items) >= max_results:
            break
    return {
        "configured": True,
        "items": list(items.values())[:max_results],
        "source": "twitch",
        "categories_scanned": len(categories),
    }
