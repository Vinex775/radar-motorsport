from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read_required(relative: str) -> str:
    path = ROOT / relative
    if not path.is_file():
        raise RuntimeError(f"Arquivo obrigatório não encontrado: {relative}. Extraia o ZIP na pasta raiz do APEX.")
    return path.read_text(encoding="utf-8")


def replace_once(content: str, old: str, new: str, label: str) -> str:
    if new in content:
        return content
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"Não consegui localizar exatamente uma vez o trecho de {label} (encontrado: {count}). Nenhum arquivo existente foi alterado.")
    return content.replace(old, new, 1)


def patch_youtube_upcoming(content: str) -> str:
    if "collectors.youtube_channels import collect_monitored_channel_videos" not in content:
        content = replace_once(
            content,
            "from collectors.youtube import SEARCH_API, _request_json, _video_details\n",
            "from collectors.youtube import SEARCH_API, _request_json, _video_details\nfrom collectors.youtube_channels import collect_monitored_channel_videos\nfrom collectors.youtube_channel_discovery import build_channel_discovery_leads\n",
            "importação do monitor de canais",
        )
    elif "build_channel_discovery_leads" not in content:
        content = replace_once(
            content,
            "from collectors.youtube_channels import collect_monitored_channel_videos\n",
            "from collectors.youtube_channels import collect_monitored_channel_videos\nfrom collectors.youtube_channel_discovery import build_channel_discovery_leads\n",
            "importação de Discovery Leads dos canais",
        )

    if "OFFICIAL_UPCOMING_CHANNELS = (" in content:
        pattern = re.compile(
            r"# Official channel IDs are more reliable than global search ranking\. Add new\n"
            r"# entries only after verifying that the channel belongs to the championship\.\n"
            r"OFFICIAL_UPCOMING_CHANNELS = \(\n.*?\n\)\n\n(?=# One-time bootstrap)",
            re.DOTALL,
        )
        content, count = pattern.subn(
            "# Permanent official channels are maintained in data/monitored_sources.json.\n\n",
            content,
            count=1,
        )
        if count != 1:
            raise RuntimeError("Não consegui substituir a lista antiga de canais oficiais do YouTube.")

    start_marker = "    # Query official channels independently of global search relevance. A\n"
    end_marker = "    if now is None:\n        local_now ="
    if "collect_monitored_channel_videos(api_key" not in content:
        start = content.find(start_marker)
        end = content.find(end_marker, start + 1) if start >= 0 else -1
        if start < 0 or end < 0:
            raise RuntimeError("Não consegui localizar o bloco de busca YouTube agendada. Nenhum arquivo existente foi alterado.")
        replacement = '''    # Read recent uploads from permanent official channels using low-quota Atom feeds.
    # The video API still verifies liveBroadcastContent and scheduledStartTime.
    channel_items, official_channels_scanned, channel_search_errors = collect_monitored_channel_videos(api_key)
    global_items = _search_upcoming(api_key, max_results, query=clean_query)

    search_items_by_id: dict[str, dict] = {}
    for item in channel_items + global_items:
        video_id = str((item.get("id") or {}).get("videoId") or "")
        if video_id and video_id not in search_items_by_id:
            search_items_by_id[video_id] = item

    # Keep enough room for scheduled videos published by every monitored channel.
    item_limit = max(50, min(250, int(max_results) * 4))
    search_items = list(search_items_by_id.values())[:item_limit]
    video_ids = [
        str((item.get("id") or {}).get("videoId") or "")
        for item in search_items
    ]
    details: dict[str, dict] = {}
    for offset in range(0, len(video_ids), 50):
        details.update(_video_details(video_ids[offset:offset + 50], api_key))

'''
        content = content[:start] + replacement + content[end:]

    # Keep a stable response shape when the YouTube API key is absent.
    content = content.replace(
        '            "future_events": [],\n            "source": "youtube_upcoming",',
        '            "future_events": [],\n            "source_leads": [],\n            "source": "youtube_upcoming",',
        1,
    )

    if "source_leads = build_channel_discovery_leads(channel_items, details)" not in content:
        content = replace_once(
            content,
            "    for offset in range(0, len(video_ids), 50):\n        details.update(_video_details(video_ids[offset:offset + 50], api_key))\n\n    if now is None:\n",
            "    for offset in range(0, len(video_ids), 50):\n        details.update(_video_details(video_ids[offset:offset + 50], api_key))\n\n    # New calendar/season announcements on trusted channels become Discovery Leads.\n    source_leads = build_channel_discovery_leads(channel_items, details)\n\n    if now is None:\n",
            "anúncios futuros publicados em canais oficiais",
        )

    content = content.replace(
        "YouTube Data API eventType=upcoming + official channel search + videos.list scheduledStartTime",
        "YouTube Data API eventType=upcoming + monitored official channel Atom feeds + videos.list scheduledStartTime",
    )
    content = content.replace("len(global_items) + official_search_results", "len(global_items) + len(channel_items)")
    content = content.replace("len(OFFICIAL_UPCOMING_CHANNELS) - len(channel_search_errors)", "official_channels_scanned")
    content = content.replace("Some official channel searches failed:", "Some official channel feeds failed:")
    content = content.replace(
        '        "items": today_items,\n        "future_events": future_events,\n        "source": "youtube_upcoming",',
        '        "items": today_items,\n        "future_events": future_events,\n        "source_leads": source_leads,\n        "source": "youtube_upcoming",',
        1,
    )
    return content


def patch_radar(content: str) -> str:
    if "from collectors.monitored_sources import load_monitored_sources" not in content:
        content = replace_once(
            content,
            "from collectors.official_schedule import fetch_official_schedule\n",
            "from collectors.official_schedule import fetch_official_schedule\nfrom collectors.monitored_sources import load_monitored_sources\nfrom collectors.monitored_discovery import discover_monitored_source_leads\n",
            "imports do registro de fontes monitoradas",
        )

    partner_helper = 'def load_monitored_watch_partners() -> list[dict[str, Any]]:\n    # Show registered official broadcast partners without classifying them as organizers.\n    existing_urls = {\n        str(source.get("url") or "").rstrip("/")\n        for source in load_watch_sources()\n    }\n    results: list[dict[str, Any]] = []\n    for monitored in load_monitored_sources():\n        if monitored.get("confidence") != "official_partner":\n            continue\n        watch_url = str(monitored.get("watch_url") or "").strip()\n        if not watch_url or watch_url.rstrip("/") in existing_urls:\n            continue\n        series_values = monitored.get("series") or []\n        if isinstance(series_values, str):\n            series_values = [series_values]\n        results.append({\n            "id": f"monitored-{monitored[\'id\']}",\n            "series": " / ".join(str(value) for value in series_values) or monitored["name"],\n            "region": monitored.get("region") or "Global",\n            "platform": monitored["name"],\n            "access": "unknown",\n            "url": watch_url,\n            "official_info": monitored.get("official_url") or monitored.get("calendar_url") or watch_url,\n            "note": monitored.get("notes") or "Official broadcast partner. Check event coverage and regional access.",\n            "confidence": "official_partner",\n        })\n        existing_urls.add(watch_url.rstrip("/"))\n    return results\n\n\n'

    old_discovery = '''def _run_discovery() -> tuple[list[dict], str | None]:
    try:
        return discover_broadcast_leads(), None
    except Exception as exc:
        return [], f"News discovery: {type(exc).__name__}: {exc}"
'''
    new_discovery = '''def _run_discovery() -> tuple[list[dict], str | None]:
    broad_records: list[dict] = []
    monitored_records: list[dict] = []
    errors: list[str] = []
    try:
        broad_records = discover_broadcast_leads()
    except Exception as exc:
        errors.append(f"Global discovery: {type(exc).__name__}: {exc}")
    try:
        monitored_records = discover_monitored_source_leads()
    except Exception as exc:
        errors.append(f"Official source monitoring: {type(exc).__name__}: {exc}")

    # Each discovery path fails independently; a working path is still saved.
    merged: dict[str, dict] = {}
    for item in broad_records + monitored_records:
        url = str(item.get("url") or "").strip()
        if url:
            merged[url] = item
    records = sorted(
        merged.values(),
        key=lambda item: item.get("published") or "",
        reverse=True,
    )
    if records:
        return records[:150], None
    if errors:
        return [], "News discovery: " + " | ".join(errors)
    return [], None
'''
    if "discover_monitored_source_leads()" not in content:
        content = replace_once(content, old_discovery, new_discovery, "buscas de Discovery Leads")

    if "def load_monitored_watch_partners()" not in content:
        content = replace_once(
            content,
            "def load_search_presets() -> list[dict[str, Any]]:\n",
            partner_helper + "def load_search_presets() -> list[dict[str, Any]]:\n",
            "parceiros oficiais em Where to Watch",
        )

    old_return = '''        "events": upcoming_events, "discoveries": discoveries, "sources": load_watch_sources(),
        "search_presets": load_search_presets(),
        "stats": {"live": 0, "upcoming": len(upcoming_events), "leads": len(discoveries)},
'''
    new_return = '''        "events": upcoming_events, "discoveries": discoveries,
        "sources": load_watch_sources() + load_monitored_watch_partners(),
        "monitored_sources": load_monitored_sources(),
        "search_presets": load_search_presets(),
        "stats": {
            "live": 0,
            "upcoming": len(upcoming_events),
            "leads": len(discoveries),
            "monitored_sources": len(load_monitored_sources()),
        },
'''
    content = replace_once(content, old_return, new_return, "resposta do dashboard")
    return content


def patch_app(content: str) -> str:
    content = content.replace("APEX-Motorsport-Radar/1.5.7", "APEX-Motorsport-Radar/1.5.8")
    content = content.replace('"version": "1.5.7"', '"version": "1.5.8"')
    old = 'self._json(200, {"sources": radar.load_watch_sources()})'
    new = 'self._json(200, {"sources": radar.load_watch_sources(), "monitored_sources": radar.load_monitored_sources()})'
    content = replace_once(content, old, new, "endpoint de fontes")
    return content


def patch_index(content: str) -> str:
    return content.replace("v1.5.0 · OPEN SOURCE", "v1.5.8 · OPEN SOURCE")


def patch_live_now(content: str) -> str:
    old = '''# Daily YouTube search.list budget:
# - Active streams: every 20 min = about 72 calls/day.
# - Upcoming streams: global + one verified official channel every 120 min
#   = about 24 calls/day. Combined estimate: 96 calls/day, below the default
#   100-call daily allowance. Do not add more channel searches without
#   increasing this TTL or reducing the active scan frequency.
'''
    new = '''# Daily YouTube search.list budget:
# - Active streams: every 20 min = about 72 global search.list calls/day.
# - Upcoming streams: one global search.list call every 120 min. Registered
#   official channels are checked through public Atom feeds and videos.list
#   enrichment, avoiding one 100-unit search.list call per channel.
# Keep these TTLs conservative to respect the default daily API allowance.
'''
    content = replace_once(content, old, new, "comentário de quota do YouTube")

    if "channel_discoveries: list[dict] = []" not in content:
        content = replace_once(
            content,
            "    future_events: list[dict] = []\n    platforms: dict[str, dict] = {}\n",
            "    future_events: list[dict] = []\n    channel_discoveries: list[dict] = []\n    platforms: dict[str, dict] = {}\n",
            "lista de anúncios publicados nos canais",
        )

    if 'channel_discoveries.extend(value.get("source_leads") or [])' not in content:
        content = replace_once(
            content,
            "                items = value.get(\"items\") or []\n",
            "                items = value.get(\"items\") or []\n                if source == \"YouTube scheduled\":\n                    channel_discoveries.extend(value.get(\"source_leads\") or [])\n",
            "captura de anúncios dos canais oficiais",
        )

    if "db.save_discoveries(channel_discoveries)" not in content:
        content = replace_once(
            content,
            "    # Persist future YouTube broadcasts in SQLite so Schedule & Events does\n",
            "    # Save upcoming calendar/season announcements from monitored official channels.\n    # A database hiccup here must not interrupt the live/schedule pipeline.\n    if channel_discoveries:\n        try:\n            db.save_discoveries(channel_discoveries)\n        except Exception:\n            pass\n\n    # Persist future YouTube broadcasts in SQLite so Schedule & Events does\n",
            "persistência de anúncios dos canais",
        )

    return content


def patch_app_js(content: str) -> str:
    helper = '''async function refreshMonitoredSources() {
  try {
    const response = await fetch('/api/refresh', {method:'POST'});
    if (!response.ok && response.status !== 207) return;
    await fetchDashboard();
  } catch (_) {
    // A temporary source outage must not interrupt the dashboard or live scanner.
  }
}
'''
    anchor = "async function fetchDashboard() {\n  const response = await fetch('/api/dashboard'); if (!response.ok) throw new Error('Could not load the dashboard.');\n  renderDashboard(await response.json());\n}\n"
    if "async function refreshMonitoredSources()" not in content:
        content = replace_once(content, anchor, anchor + helper, "função de atualização automática")

    old_tail = '''fetchDashboard().then(() => scanLiveNow(false)).catch(error => showToast(error.message, true));
window.setInterval(checkUpcomingAlerts, 60_000);
window.setInterval(() => scanLiveNow(false), 5 * 60_000);
'''
    new_tail = '''fetchDashboard().then(() => scanLiveNow(false)).catch(error => showToast(error.message, true));
// Refresh permanent organizer/channel monitors on startup and every six hours while APEX is open, including background tabs.
window.setTimeout(refreshMonitoredSources, 4_000);
window.setInterval(checkUpcomingAlerts, 60_000);
window.setInterval(() => scanLiveNow(false), 5 * 60_000);
window.setInterval(refreshMonitoredSources, 6 * 60 * 60 * 1000);
'''
    content = replace_once(content, old_tail, new_tail, "agendamento periódico no navegador")
    content = content.replace(
        "const officialSources = state.sources.filter(source => ['official','regional'].includes(source.confidence));",
        "const officialSources = state.sources.filter(source => ['official','regional','official_partner'].includes(source.confidence));",
    )
    content = content.replace(
        '<div class="source-evidence">${source.confidence === "official" ? "OFFICIAL REFERENCE" : "OFFICIAL REGIONAL GUIDE"} · checked on ${escapeHtml(source.last_checked || "not provided")}</div>',
        '<div class="source-evidence">${source.confidence === "official" ? "OFFICIAL REFERENCE" : source.confidence === "official_partner" ? "OFFICIAL BROADCAST PARTNER" : "OFFICIAL REGIONAL GUIDE"}${source.confidence === "official_partner" ? "" : " · checked on " + escapeHtml(source.last_checked || "not provided")}</div>',
    )
    # The scheduled-video collector is internal; show only one YouTube status row.
    content = content.replace(
        "const platformSummary = Object.entries(platforms).map(([name, status]) => {",
        "const platformSummary = Object.entries(platforms).filter(([name]) => name !== 'YouTube scheduled').map(([name, status]) => {",
    )
    return content


def main() -> int:
    relative_files = {
        "collectors/youtube_upcoming.py": patch_youtube_upcoming(read_required("collectors/youtube_upcoming.py")),
        "radar.py": patch_radar(read_required("radar.py")),
        "app.py": patch_app(read_required("app.py")),
        "collectors/live_now.py": patch_live_now(read_required("collectors/live_now.py")),
        "static/app.js": patch_app_js(read_required("static/app.js")),
        "templates/index.html": patch_index(read_required("templates/index.html")),
    }

    # Preflight every marker before writing: the operation is all-or-nothing.
    for relative, content in relative_files.items():
        if not content.strip():
            raise RuntimeError(f"Resultado vazio ao preparar {relative}.")

    for relative, content in relative_files.items():
        (ROOT / relative).write_text(content, encoding="utf-8", newline="\n")

    print("APEX 1.5.8 — fontes permanentes instaladas.")
    print("Arquivos existentes atualizados: " + ", ".join(relative_files))
    print("Novos arquivos: collectors/monitored_sources.py, collectors/youtube_channels.py,")
    print("               collectors/monitored_discovery.py, collectors/youtube_channel_discovery.py,")
    print("               data/monitored_sources.json")
    print("Testes adicionados: tests/test_monitored_sources.py, tests/test_youtube_channels.py,")
    print("                    tests/test_monitored_discovery.py, tests/test_youtube_channel_discovery.py")
    print("O banco SQLite, .env, data/official_schedule.json e data/watch_sources.json não foram alterados.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        print("Nenhum dos arquivos existentes foi alterado. Confira se o ZIP foi extraído na raiz do APEX.", file=sys.stderr)
        raise SystemExit(1)
