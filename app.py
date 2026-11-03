"""Servidor HTTP local sem framework ou dependências de interface externas."""
from __future__ import annotations

import json
import mimetypes
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import db
import radar
from collectors.youtube import buscar_lives as buscar_lives_youtube
from collectors.discovery import buscar_pistas_personalizadas

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
TEMPLATE = ROOT / "templates" / "index.html"
ACCESS_VALUES = {"free", "subscription", "ppv", "unknown"}


def valid_http_url(value: str | None) -> bool:
    if not value:
        return True
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _manual_event(data: dict) -> tuple[dict | None, str | None]:
    required = ["name", "series", "start", "platform", "access"]
    missing = [field for field in required if not str(data.get(field, "")).strip()]
    if missing:
        return None, "Preencha os campos obrigatórios: " + ", ".join(missing)
    if data["access"] not in ACCESS_VALUES:
        return None, "Tipo de acesso inválido."
    for field in ("stream_url", "watch_url"):
        if not valid_http_url(data.get(field)):
            return None, f"O campo {field} precisa ser um link http(s) válido."
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
                return None, "O fim precisa ser depois do início."
    except (TypeError, ValueError):
        return None, "Data/hora inválida."

    name = str(data["name"]).strip()[:180]
    series = str(data["series"]).strip()[:100]
    return {
        "external_id": f"manual:{name.lower()}:{start_utc}",
        "name": name,
        "series": series,
        "category": str(data.get("category") or "Outros")[:100],
        "kind": str(data.get("kind") or "Corrida")[:100],
        "start": start_utc,
        "end": end_utc,
        "platform": str(data["platform"]).strip()[:100],
        "access": data["access"],
        "stream_url": data.get("stream_url"),
        "watch_url": data.get("watch_url"),
        "region": str(data.get("region") or "Global")[:100],
        "confidence": "user",
        "source_name": "Cadastro manual",
        "source_url": data.get("stream_url") or data.get("watch_url"),
    }, None


class RadarHandler(BaseHTTPRequestHandler):
    server_version = "APEX-Motorsport-Radar/1.1"

    def log_message(self, format: str, *args) -> None:
        # Mantém o terminal limpo, exceto erros HTTP.
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
                raise ValueError("Tamanho de requisição inválido.")
            return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("O corpo da requisição precisa ser JSON válido.") from exc

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            try:
                self._send(200, TEMPLATE.read_bytes(), "text/html; charset=utf-8")
            except OSError:
                self._json(500, {"error": "Arquivo da interface não encontrado."})
        elif path.startswith("/static/"):
            name = path.removeprefix("/static/")
            if not re.fullmatch(r"[a-zA-Z0-9_.-]+", name):
                self._json(400, {"error": "Caminho inválido."}); return
            file_path = (STATIC / name).resolve()
            if file_path.parent != STATIC.resolve() or not file_path.is_file():
                self._json(404, {"error": "Arquivo não encontrado."}); return
            content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            charset = "; charset=utf-8" if content_type.startswith(("text/", "application/javascript")) else ""
            self._send(200, file_path.read_bytes(), content_type + charset)
        elif path == "/api/dashboard":
            self._json(200, radar.dashboard_data())
        elif path == "/api/health":
            self._json(200, {"ok": True, "app": "APEX Motorsport Radar", "version": "1.1.0"})
        elif path == "/api/sources":
            self._json(200, {"sources": radar.load_watch_sources()})
        elif path == "/api/discover-search":
            query = parse_qs(urlparse(self.path).query).get("q", [""])[0].strip()
            if len(query) < 2:
                self._json(400, {"error": "Digite pelo menos 2 caracteres para pesquisar."}); return
            try:
                items = buscar_pistas_personalizadas(query)
                db.save_discoveries(items)
                self._json(200, {"query": query, "items": items, "count": len(items)})
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
            except OSError as exc:
                self._json(502, {"error": str(exc)})
        elif path == "/api/youtube-live":
            query = parse_qs(urlparse(self.path).query).get("q", [""])[0].strip()
            if not query:
                self._json(400, {"error": "Digite uma categoria, campeonato ou evento."}); return
            try:
                self._json(200, buscar_lives_youtube(query))
            except RuntimeError as exc:
                self._json(502, {"configured": True, "error": str(exc)})
        else:
            self._json(404, {"error": "Rota não encontrada."})

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
            self._json(201, {"ok": True, "message": "Evento adicionado ao radar."})
        else:
            self._json(404, {"error": "Rota não encontrada."})


def serve(host: str = "127.0.0.1", port: int = 5000) -> None:
    db.init_db()
    server = ThreadingHTTPServer((host, port), RadarHandler)
    try:
        print(f"\n🏁 APEX — MOTORSPORT RADAR\nAbra http://{host}:{port} no navegador.\nPressione Ctrl+C para encerrar.\n")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando o Motorsport Radar...")
    finally:
        server.server_close()
