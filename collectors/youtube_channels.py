"""Low-quota scheduled-video discovery from registered official YouTube channels.

Instead of one expensive search.list request per channel, this collector reads
YouTube's public channel Atom feeds and enriches the returned video IDs with a
small number of videos.list requests. Scheduled timestamps are still verified
from YouTube's liveStreamingDetails before a video can enter APEX Schedule.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from collectors.monitored_sources import get_youtube_sources
from collectors.youtube import API, _request_json

CHANNELS_API = f"{API}/channels"
ATOM_NS = "http://www.w3.org/2005/Atom"
YOUTUBE_NS = "http://www.youtube.com/xml/schemas/2015"


@lru_cache(maxsize=128)
def _resolve_channel_id_cached(handle: str, api_key: str) -> str:
    params = urlencode({"part": "id", "forHandle": handle, "key": api_key})
    payload = _request_json(f"{CHANNELS_API}?{params}", api_key)
    items = payload.get("items") or []
    return str(items[0].get("id") or "") if items else ""


def _channel_id(source: dict, api_key: str) -> str:
    channel = source.get("youtube_channel") or {}
    direct_id = str(channel.get("channel_id") or "").strip()
    if direct_id:
        return direct_id
    handle = str(channel.get("handle") or "").strip()
    if not handle:
        return ""
    if not handle.startswith("@"):
        handle = "@" + handle
    return _resolve_channel_id_cached(handle, api_key)


def _read_channel_feed(source: dict, api_key: str, max_per_channel: int) -> tuple[list[dict], str | None]:
    source_name = str(source.get("name") or "Official YouTube channel")
    try:
        channel_id = _channel_id(source, api_key)
        if not channel_id:
            return [], f"{source_name}: YouTube channel ID could not be resolved"
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        request = Request(feed_url, headers={"User-Agent": "Mozilla/5.0 (compatible; APEX-Motorsport-Radar/1.5.8)"})
        with urlopen(request, timeout=12) as response:
            payload = response.read()
        root = ElementTree.fromstring(payload)
        entries = root.findall(f"{{{ATOM_NS}}}entry")[:max(1, min(int(max_per_channel), 15))]
        results: list[dict] = []
        for entry in entries:
            video_id_node = entry.find(f"{{{YOUTUBE_NS}}}videoId")
            channel_id_node = entry.find(f"{{{YOUTUBE_NS}}}channelId")
            title_node = entry.find(f"{{{ATOM_NS}}}title")
            published_node = entry.find(f"{{{ATOM_NS}}}published")
            video_id = (video_id_node.text or "").strip() if video_id_node is not None else ""
            if not video_id:
                continue
            results.append({
                "id": {"videoId": video_id},
                "snippet": {
                    "title": (title_node.text or "").strip() if title_node is not None else "",
                    "channelTitle": source_name,
                    "channelId": (channel_id_node.text or "").strip() if channel_id_node is not None else channel_id,
                    "publishedAt": (published_node.text or "").strip() if published_node is not None else None,
                    "monitoringSourceId": source.get("id"),
                    "monitoringSourceName": source_name,
                    "monitoringSeries": source.get("series") or [],
                },
            })
        return results, None
    except (RuntimeError, HTTPError, URLError, TimeoutError, OSError, ElementTree.ParseError, ValueError) as exc:
        # One source outage must never prevent the other channels from being scanned.
        return [], f"{source_name}: {type(exc).__name__}: {exc}"


def collect_monitored_channel_videos(
    api_key: str,
    max_per_channel: int = 12,
) -> tuple[list[dict], int, list[str]]:
    """Read recent video IDs from all enabled registered official channels."""
    sources = get_youtube_sources()
    if not sources:
        return [], 0, []

    feeds: list[dict] = []
    errors: list[str] = []
    scanned = 0
    with ThreadPoolExecutor(max_workers=min(8, len(sources))) as pool:
        futures = {
            pool.submit(_read_channel_feed, source, api_key, max_per_channel): source
            for source in sources
        }
        for future in as_completed(futures):
            items, error = future.result()
            if error:
                errors.append(error)
                continue
            scanned += 1
            feeds.extend(items)

    deduplicated: dict[str, dict] = {}
    for item in feeds:
        video_id = str((item.get("id") or {}).get("videoId") or "")
        if video_id:
            deduplicated[video_id] = item
    return list(deduplicated.values()), scanned, errors
