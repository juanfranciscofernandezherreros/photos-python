"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from .. import web_server as _shared

# Endpoint implementations retain access to the application's shared services,
# models and state without duplicating business infrastructure.
globals().update({
    name: value
    for name, value in vars(_shared).items()
    if not name.startswith("__")
})

router = APIRouter()

@router.get("/api/albums")
def get_albums(_auth: dict = Depends(require_login)):
    """List all albums with photo count and a resolved cover path."""
    albums = repo.load_albums()
    out = [{"id": a["id"], "name": a["name"], "cover": a["cover"],
             "created": a["created"], "count": a["count"]} for a in albums]
    return {"albums": out, "total": len(out)}
