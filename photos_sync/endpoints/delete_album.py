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

@router.delete("/api/albums/{album_id}")
def delete_album(album_id: str, _auth: dict = Depends(require_login)):
    """Delete an album. The underlying photos are never touched."""
    deleted = repo.delete_album(album_id)
    if not deleted:
        raise HTTPException(404, "Album not found")
    remaining = repo.load_albums()
    return {"ok": True, "total": len(remaining)}
