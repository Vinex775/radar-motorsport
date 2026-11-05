"""Discover active motorsport livestreams through the official Kick API."""
from __future__ import annotations

import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from collectors.discovery import is_motorsport_result, is_reaction_or_commentary
from collectors.live_filter import VIDEO_GAME_TITLE_RE

TOKEN_URL = "https://id.kick.com/oauth/token"
API_BASE = "https://api.kick.com"
CATEGORY_NAMES = (
    "Motorsports", "Motorsport", "Auto Racing", "Racing", "Karting", "Rally",
    "Motocross", "Speedway", "Drifting", "Drag Racing", "Hillclimb", "Enduro",
    "Autosuunnistus", "Folkrace", "Rallisprint", "Stock Car", "Tractor Pulling",
)
_TOKEN: str | None = None
_TOKEN_EXPIRES = 0.0
_TOKEN_CREDENTIALS: tuple[str, str] | None = None


def _error_detail(exc: HTTPError) -> tuple[str, str | None]:
    """Extract safe diagnostic details without exposing credentials or URLs."""
    try:
        raw = exc.read(2048).decode("utf-8", errors="replace")
    except Exception:
        raw = ""
    detail = ""
    try:
        payload = json.loads(raw)
        detail = str(payload.get("message") or payload.get("error_description") or payload.get("error") or "")
    except (ValueError, AttributeError):
        # Cloudflare may return HTML instead of the API's JSON error object.
        clean = re.sub(r"<[^>]+>", " ", raw)
        clean = re.sub(r"\s+", " ", clean).strip()
        if clean:
            detail = clean[:180]
    cf_ray = None
    try:
        cf_ray = exc.headers.get("CF-Ray") if exc.headers else None
    except AttributeError:
        pass
    return detail, cf_ray


def _request_json(
    url: str,
    headers: dict | None = None,
    data: bytes | None = None,
    context: str = "API request",
) -> dict:
    request_headers = {"Accept": "application/json", **(headers or {})}
    request = Request(url, headers=request_headers, data=data)
    try:
        with urlopen(request, timeout=18) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail, cf_ray = _error_detail(exc)
        message = f"Kick {context} returned HTTP {exc.code}."
        if detail:
            message += f" Provider detail: {detail}"
        if cf_ray:
            message += f" Cloudflare Ray ID: {cf_ray}."
        raise RuntimeError(message) from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(f"Could not query Kick ({context}): {exc}") from exc


def _credentials() -> tuple[str, str]:
    return os.environ.get("KICK_CLIENT_ID", "").strip(), os.environ.get("KICK_CLIENT_SECRET", "").strip()


def _app_token(client_id: str, client_secret: str) -> str:
    global _TOKEN, _TOKEN_EXPIRES, _TOKEN_CREDENTIALS
    credentials = (client_id, client_secret)
    if _TOKEN and _TOKEN_CREDENTIALS == credentials and time.monotonic() < _TOKEN_EXPIRES - 60:
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
        context="OAuth token endpoint",
    )
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("Kick OAuth token endpoint did not return an app access token.")
    _TOKEN = token
    _TOKEN_CREDENTIALS = credentials
    _TOKEN_EXPIRES = time.monotonic() + int(payload.get("expires_in", 3600))
    return token


def _api_get(path: str, params: list[tuple[str, str]], token: str) -> dict:
    return _request_json(
        f"{API_BASE}{path}?{urlencode(params)}",
        {"Authorization": f"Bearer {token}", "User-Agent": "APEX-Motorsport-Radar"},
        context=f"API endpoint {path}",
    )


CATEGORY_LABEL_RE = re.compile(
    r"^(?:rally|racing|auto racing|car racing|kart|karting|motorsport|motorsports|"
    r"motocross|speedway|drifting|drift|drag racing|hill ?climb|enduro|stock car|"
    r"short track racing|folkrace|rallisprint|autosuunnistus|tractor pulling)$",
    re.IGNORECASE,
)


def _is_motorsport(value: str) -> bool:
    clean = value.strip()
    if VIDEO_GAME_TITLE_RE.search(clean):
        return False
    return bool(CATEGORY_LABEL_RE.fullmatch(clean)) or is_motorsport_result(clean, "")


def search_live_streams(max_results: int = 300) -> dict:
    """Return active Kick livestreams in motorsport-related categories."""
    client_id, client_secret = _credentials()
    if not client_id or not client_secret:
        return {
            "configured": False,
            "items": [],
            "source": "kick",
            "message": "Set KICK_CLIENT_ID and KICK_CLIENT_SECRET to enable Kick live discovery.",
        }

    token = _app_token(client_id, client_secret)
    categories_by_id: dict[str, dict] = {}
    # The API accepts comma-separated names and constrains the query length.
    category_batches: list[list[str]] = []
    current_batch: list[str] = []
    for name in CATEGORY_NAMES:
        candidate = ",".join([*current_batch, name])
        if current_batch and len(candidate) > 90:
            category_batches.append(current_batch)
            current_batch = [name]
        else:
            current_batch.append(name)
    if current_batch:
        category_batches.append(current_batch)

    for batch in category_batches:
        category_params = [("name", ",".join(batch)), ("limit", "1000")]
        category_payload = _api_get("/public/v2/categories", category_params, token)
        for category in (category_payload.get("data") or []):
            name = str(category.get("name") or "")
            category_id = category.get("id")
            if category_id is not None and _is_motorsport(name):
                categories_by_id[str(category_id)] = {"id": str(category_id), "name": name}
    relevant_categories = list(categories_by_id.values())

    params: list[tuple[str, str]] = [("limit", "1000")]
    params.extend(("category_id", item["id"]) for item in relevant_categories[:25])
    # Kick sorts this endpoint oldest-first, so paginate and sort matches newest-first.
    streams: list[dict] = []
    cursor = None
    pages_scanned = 0
    for _ in range(10):
        page_params = list(params)
        if cursor:
            page_params.append(("cursor", cursor))
        page = _api_get("/public/v2/livestreams", page_params, token)
        page_streams = page.get("data") or []
        pages_scanned += 1
        streams.extend(page_streams)
        cursor = (page.get("pagination") or {}).get("next_cursor")
        if not cursor or not page_streams:
            break

    items: dict[str, dict] = {}
    for stream in streams:
        category = stream.get("category") or {}
        title = str(stream.get("title") or "")
        category_name = str(category.get("name") or "")
        user = stream.get("broadcaster_user") or {}
        channel = stream.get("channel") or {}
        username = str(user.get("username") or channel.get("slug") or "")
        tags = " ".join(stream.get("tags") or [])
        if not (_is_motorsport(category_name) or is_motorsport_result(title, tags)):
            continue
        if is_reaction_or_commentary(title, tags):
            continue
        stream_id = str(stream.get("id") or f"{username}:{stream.get('started_at', '')}")
        if not username:
            continue
        items[stream_id] = {
            "id": f"kick:{stream_id}",
            "title": title or category_name or "Live motorsport stream",
            "channel": username,
            "category": category_name or "Motorsport",
            "platform": "Kick",
            "url": f"https://kick.com/{username}",
            "thumbnail": stream.get("thumbnail"),
            "started_at": stream.get("started_at"),
            "viewers": int(stream.get("viewer_count") or 0),
            "language": stream.get("language_code"),
            "access": "unknown",
            "status": "live_now",
            "is_verified_live": True,
            "verification": "Kick Public API active livestream endpoint",
            "note": "Kick confirms that this channel is live. APEX filters out known replays, games, and support activity; open the stream to verify the actual race feed.",
        }
    ordered = sorted(items.values(), key=lambda item: str(item.get("started_at") or ""), reverse=True)
    return {
        "configured": True,
        "items": ordered[:max_results],
        "source": "kick",
        "categories_scanned": len(relevant_categories),
        "pages_scanned": pages_scanned,
    }
