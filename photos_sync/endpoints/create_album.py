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

@router.post("/api/albums")
def create_album(req: AlbumCreateIn, _auth: dict = Depends(require_login)):
    """Create a new empty album. Returns the created album with its id."""
    import uuid
    from datetime import datetime

    name = (req.name or "").strip()
    if not name:
        raise HTTPException(400, "Album name cannot be empty")

    album = repo.create_album(
        album_id=f"alb_{uuid.uuid4().hex[:8]}",
        name=name,
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    return {"ok": True, "album": album}
