"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    repo,
    require_login,
)

router = APIRouter()

@router.get("/api/albums")
def get_albums(_auth: dict = Depends(require_login)):
    """List all albums with photo count and a resolved cover path."""
    albums = repo.load_albums()
    out = [{"id": a["id"], "name": a["name"], "cover": a["cover"],
             "created": a["created"], "count": a["count"]} for a in albums]
    return {"albums": out, "total": len(out)}
