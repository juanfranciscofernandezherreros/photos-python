"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    repo,
    require_admin,
)

router = APIRouter()

@router.get("/api/diag")
def diagnostic(_admin: dict = Depends(require_admin)):
    """Diagnostic endpoint — quick overview of what's in the database.
    Useful for verifying that ingest is actually landing in the tables."""
    from ..db import get_engine
    engine = get_engine()
    return {
        "db_dialect": engine.dialect.name,
        "db_url":     str(engine.url).replace(engine.url.password or "", "***"),
        "counts": {
            "captures":            len(repo.load_captures()),
            "day_summaries":       len(repo.load_summaries()),
            "source_folders":      len(repo.load_source_folders()),
            "ssh_connections":     len(repo.load_ssh_connections()),
            "webdav_connections":  len(repo.load_webdav_connections()),
            "albums":              len(repo.load_albums()),
            "trash":               repo.trash_count(),
            "users":               repo.user_count(),
        },
        "destination": repo.load_destination_config(),
    }
