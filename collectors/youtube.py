"""Pesquisa vídeos que o YouTube Data API identifica como transmissões ativas.

A API key é opcional e deve ser fornecida por variável de ambiente para não
ficar gravada no repositório.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://www.googleapis.com/youtube/v3/search"


def buscar_lives(query: str, max_results: int = 25) -> dict:
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        return {"configured": False, "items": []}

    params = urlencode({
        "part": "snippet",
        "q": query[:150],
        "type": "video",
        "eventType": "live",
        "maxResults": max(1, min(int(max_results), 25)),
        "order": "relevance",
        "key": api_key,
    })
    request = Request(API + "?" + params, headers={"User-Agent": "MotorsportRadar/1.0"})
    try:
        with urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        # Não devolve a URL da requisição, pois ela contém a API key.
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            detail = ""
        raise RuntimeError(detail or f"YouTube API respondeu HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(f"Não foi possível consultar o YouTube: {exc}") from exc

    items = []
    for item in payload.get("items", []) or []:
        video_id = (item.get("id") or {}).get("videoId")
        snippet = item.get("snippet") or {}
        if not video_id:
            continue
        items.append({
            "title": snippet.get("title") or "Transmissão ao vivo",
            "channel": snippet.get("channelTitle") or "Canal do YouTube",
            "published": snippet.get("publishedAt"),
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "platform": "YouTube",
            "access": "unknown",
            "is_verified_live": True,
            "note": "O YouTube marcou este vídeo como transmissão ao vivo. Preço e restrição regional ainda precisam ser confirmados.",
        })
    return {"configured": True, "items": items}
