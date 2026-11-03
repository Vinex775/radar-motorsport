from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(__import__("os").environ.get("RADAR_DB", ROOT / "data" / "radar.sqlite3"))


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            external_id TEXT NOT NULL,
            name TEXT NOT NULL,
            series TEXT NOT NULL DEFAULT 'Motorsport',
            category TEXT NOT NULL DEFAULT 'Outros',
            kind TEXT NOT NULL DEFAULT 'Evento',
            start_utc TEXT,
            end_utc TEXT,
            platform TEXT NOT NULL DEFAULT 'Não identificada',
            access TEXT NOT NULL DEFAULT 'unknown',
            stream_url TEXT,
            watch_url TEXT,
            region TEXT DEFAULT 'Global',
            confidence TEXT DEFAULT 'unknown',
            source_name TEXT,
            source_url TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source, external_id)
        );
        CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_utc);
        CREATE TABLE IF NOT EXISTS discoveries (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            summary TEXT,
            url TEXT NOT NULL UNIQUE,
            published_utc TEXT,
            source_name TEXT,
            series TEXT,
            platform TEXT,
            access TEXT,
            note TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)


def upsert_event(event: dict[str, Any], source: str) -> None:
    with connect() as conn:
        conn.execute("""
        INSERT INTO events (
            source, external_id, name, series, category, kind, start_utc, end_utc,
            platform, access, stream_url, watch_url, region, confidence, source_name, source_url, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(source, external_id) DO UPDATE SET
            name=excluded.name, series=excluded.series, category=excluded.category,
            kind=excluded.kind, start_utc=excluded.start_utc, end_utc=excluded.end_utc,
            platform=excluded.platform, access=excluded.access, stream_url=excluded.stream_url,
            watch_url=excluded.watch_url, region=excluded.region, confidence=excluded.confidence,
            source_name=excluded.source_name, source_url=excluded.source_url, updated_at=CURRENT_TIMESTAMP
        """, (
            source, event.get("external_id"), event.get("name"), event.get("series", "Motorsport"),
            event.get("category", "Outros"), event.get("kind", "Evento"), event.get("start"),
            event.get("end"), event.get("platform", "Não identificada"), event.get("access", "unknown"),
            event.get("stream_url"), event.get("watch_url"), event.get("region", "Global"),
            event.get("confidence", "unknown"), event.get("source_name"), event.get("source_url"),
        ))


def save_discoveries(items: list[dict[str, Any]]) -> None:
    with connect() as conn:
        for item in items:
            conn.execute("""
            INSERT INTO discoveries (id, title, summary, url, published_utc, source_name, series, platform, access, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title=excluded.title, summary=excluded.summary, published_utc=excluded.published_utc,
                source_name=excluded.source_name, series=excluded.series, platform=excluded.platform,
                access=excluded.access, note=excluded.note, updated_at=CURRENT_TIMESTAMP
            """, (
                item["id"], item["title"], item.get("summary"), item["url"], item.get("published"),
                item.get("source_name"), item.get("series"), item.get("platform"), item.get("access"), item.get("note"),
            ))


def get_events() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM events ORDER BY start_utc IS NULL, start_utc ASC").fetchall()
    return [dict(row) for row in rows]


def purge_irrelevant_discoveries() -> int:
    """Remove do SQLite pistas antigas que não passam no filtro de motorsport."""
    from collectors.discovery import is_motorsport_result

    with connect() as conn:
        rows = conn.execute("SELECT id, title, summary FROM discoveries").fetchall()
        invalid_ids = [
            row["id"] for row in rows
            if not is_motorsport_result(row["title"], row["summary"] or "")
        ]
        if invalid_ids:
            conn.executemany("DELETE FROM discoveries WHERE id = ?", [(item_id,) for item_id in invalid_ids])
    return len(invalid_ids)


def get_discoveries(limit: int = 60) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM discoveries ORDER BY published_utc DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]


def save_manual_event(event: dict[str, Any]) -> None:
    upsert_event(event, "manual")


def get_setting(key: str) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
