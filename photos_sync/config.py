"""
config.py — Application-wide constants for Photos Sync.

JSON files have been replaced by PostgreSQL (SQLAlchemy).
Set DATABASE_URL to override the default connection string.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR: Path     = Path.home() / "PhotosSync"
ORGANIZED_DIR: Path = BASE_DIR / "screenshots_agrupados"
ZIPS_DIR: Path     = ORGANIZED_DIR / "Comprimidos"

_DATA_DIR: Path    = BASE_DIR / "data"
THUMBS_DIR: Path   = _DATA_DIR / "thumbs"
ORCHESTRATOR_LOG: str = str(_DATA_DIR / "orquestador.log")

VALID_EXTENSIONS: set[str] = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp",
    ".webp", ".tiff", ".heic", ".mp4", ".mov",
}

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://localhost/photos_sync",
)

# ── Bootstrap ─────────────────────────────────────────────────────────────────
_DATA_DIR.mkdir(parents=True, exist_ok=True)
THUMBS_DIR.mkdir(parents=True, exist_ok=True)
