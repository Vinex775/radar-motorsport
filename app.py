"""Local HTTP server with no framework or external UI dependencies."""
from __future__ import annotations

import json
import mimetypes
import re
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import db
import radar
from config import load_environment

# Load local API credentials before importing platform collectors.
load_environment()

from collectors.live_now import search_all_live_streams
from collectors.discovery import search_custom_discovery_leads

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
TEMPLATE = ROOT / "templates" / "index.html"
ACCESS_VALUES = {"free", "subscription", "ppv", "unknown"}


def _browser_timezone(request_target: str):
    """Resolve the browser's timezone, falling back to its current UTC offset.

    The IANA name handles daylight-saving transitions when tzdata is available.
    The numeric offset works on Windows even when the OS has no IANA timezone DB.
    """
    query = parse_qs(urlparse(request_target).query)
    zone_name = (query.get("time_zone") or [""])[0].strip()
    if zone_name and len(zone_name) <= 80:
        try:
            return ZoneInfo(zone_name)
        except Exception:
            pass

    raw_offset = (query.get("utc_offset_minutes") or [""])[0]
    try:
        utc_minus_local_minutes = int(raw_offset)
    except (TypeError, ValueError):
        return None
    if not -840 <= utc_minus_local_minutes <= 840:
        return None
    return timezone(timedelta(minutes=-utc_minus_local_minutes))


def valid_http_url(value: str | None) -> bool:
    if not value:
        return True
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _manual_event(data: dict) -> tuple[dict | None, str | None]:
    required = ["name", "series", "start", "platform", "access"]
    missing = [field for field in required if not str(data.get(field, "")).strip()]
    if missing:
        return None, "Required fields: " + ", ".join(missing)
    if data["access"] not in ACCESS_VALUES:
        return None, "Invalid access type."
    for field in ("stream_url", "watch_url"):
        if not valid_http_url(data.get(field)):
            return None, f"The {field} field must be a valid HTTP(S) URL."
    try:
        start = datetime.fromisoformat(data["start"].replace("Z", "+00:00"))
        if start.tzinfo is None:
            start = start.astimezone()
        start_utc = start.astimezone(timezone.utc).isoformat()
        end_utc = None
        if data.get("end"):
            end = datetime.fromisoformat(data["end"].replace("Z", "+00:00"))
            if end.tzinfo is None:
                end = end.astimezone()
            end_utc = end.astimezone(timezone.utc).isoformat()
            if end_utc <= start_utc:
                return None, "The end time must be after the start time."
    except (TypeError, ValueError):
        return None, "Invalid date/time."

    name = str(data["name"]).strip()[:180]
    series = str(data["series"]).strip()[:100]
    return {
        "external_id": f"manual:{name.lower()}:{start_utc}",
        "name": name,
        "series": series,
        "category": str(data.get("category") or "Other")[:100],
        "kind": str(data.get("kind") or "Race")[:100],
        "start": start_utc,
        "end": end_utc,
        "platform": str(data["platform"]).strip()[:100],
        "access": data["access"],
        "stream_url": data.get("stream_url"),
        "watch_url": data.get("watch_url"),
        "region": str(data.get("region") or "Global")[:100],
        "confidence": "user",
        "source_name": "Manual entry",
        "source_url": data.get("stream_url") or data.get("watch_url"),
    }, None


class RadarHandler(BaseHTTPRequestHandler):
    server_version = "APEX-Motorsport-Radar/1.5.7"

    def log_message(self, format: str, *args) -> None:
        if args and str(args[1]).startswith("4"):
            super().log_message(format, *args)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 1_000_000:
                raise ValueError("Invalid request size.")
            return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Request body must be valid JSON.") from exc

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            try:
                # Send the browser's local timezone with dashboard/live API calls.
                # This script must run before app.js starts its first fetch.
                page = TEMPLATE.read_bytes()
                app_script = b'<script src="/static/app.js"></script>'
                helper_script = b'<script src="/static/live-today.js"></script>'
                timezone_script = b'''<script>
(() => {
  const nativeFetch = window.fetch.bind(window);
  const browserTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
  const utcOffsetMinutes = new Date().getTimezoneOffset();
  window.fetch = (input, init) => {
    if (typeof input === 'string') {
      try {
        const url = new URL(input, window.location.href);
        if (url.origin === window.location.origin && ['/api/dashboard', '/api/live-now', '/api/youtube-live'].includes(url.pathname)) {
          if (browserTimeZone) url.searchParams.set('time_zone', browserTimeZone);
          url.searchParams.set('utc_offset_minutes', String(utcOffsetMinutes));
          input = url.toString();
        }
      } catch (_) { /* Preserve the original request if URL parsing fails. */ }
    }
    return nativeFetch(input, init);
  };
})();
</script>'''
                if app_script in page:
                    if timezone_script not in page:
                        page = page.replace(app_script, timezone_script + app_script, 1)
                    if helper_script not in page:
                        page = page.replace(app_script, app_script + helper_script, 1)
                self._send(200, page, "text/html; charset=utf-8")
            except OSError:
                self._json(500, {"error": "Dashboard template not found."})
        elif path.startswith("/static/"):
            name = path.removeprefix("/static/")
            if not re.fullmatch(r"[a-zA-Z0-9_.-]+", name):
                self._json(400, {"error": "Invalid path."}); return
            file_path = (STATIC / name).resolve()
            if file_path.parent != STATIC.resolve() or not file_path.is_file():
                self._json(404, {"error": "File not found."}); return
            content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            charset = "; charset=utf-8" if content_type.startswith(("text/", "application/javascript")) else ""
            self._send(200, file_path.read_bytes(), content_type + charset)
        elif path == "/api/dashboard":
            self._json(200, radar.dashboard_data(local_tz=_browser_timezone(self.path)))
        elif path == "/api/health":
            self._json(200, {"ok": True, "app": "APEX Motorsport Radar", "version": "1.5.7"})
        elif path == "/api/sources":
            self._json(200, {"sources": radar.load_watch_sources()})
        elif path == "/api/discover-search":
            query = parse_qs(urlparse(self.path).query).get("q", [""])[0].strip()
            if len(query) < 2:
                self._json(400, {"error": "Enter at least 2 characters to search."}); return
            try:
                items = search_custom_discovery_leads(query)
                db.save_discoveries(items)
                future_items = [item for item in items if item.get("lead_status") == "upcoming_lead"]
                self._json(200, {"query": query, "items": future_items, "count": len(future_items)})
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
            except OSError as exc:
                self._json(502, {"error": str(exc)})
        elif path in {"/api/youtube-live", "/api/live-now"}:
            query = parse_qs(urlparse(self.path).query).get("q", [""])[0].strip() or "motorsport"
            try:
                self._json(200, search_all_live_streams(query, local_tz=_browser_timezone(self.path)))
            except RuntimeError as exc:
                self._json(502, {"mode": "live_now", "error": str(exc), "items": [], "platforms": {}})
        else:
            self._json(404, {"error": "Route not found."})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/refresh":
            result = radar.refresh_all()
            self._json(200 if result["ok"] else 207, result)
        elif path == "/api/events":
            try:
                data = self._read_json()
            except ValueError as exc:
                self._json(400, {"error": str(exc)}); return
            event, error = _manual_event(data)
            if error:
                self._json(400, {"error": error}); return
            db.save_manual_event(event)
            self._json(201, {"ok": True, "message": "Event added to APEX."})
        else:
            self._json(404, {"error": "Route not found."})


def serve(host: str = "127.0.0.1", port: int = 5000) -> None:
    db.init_db()
    server = ThreadingHTTPServer((host, port), RadarHandler)
    try:
        print(f"\n🏁 APEX — MOTORSPORT RADAR\nOpen http://{host}:{port} in your browser.\nPress Ctrl+C to stop.\n")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down APEX Motorsport Radar...")
    finally:
        server.server_close()
