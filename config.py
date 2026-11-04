"""Small .env reader for local APEX development; no third-party dependency."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_environment(path: Path | None = None) -> None:
    """Load KEY=VALUE entries from .env without overriding existing variables."""
    env_path = path or (ROOT / ".env")
    try:
        lines = env_path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)
