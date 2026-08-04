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

@router.patch("/api/albums/{album_id}")
def update_album(album_id: str, req: AlbumRenameIn, _auth: dict = Depends(require_login)):
    """Rename an album and/or set its cover photo."""
    album = repo.get_album(album_id)
    if album is None:
        raise HTTPException(404, "Album not found")

    if req.name is not None:
        new_name = req.name.strip()
        if not new_name:
            raise HTTPException(400, "Album name cannot be empty")
        repo.update_album_name(album_id, new_name)
        album["name"] = new_name
    if req.cover is not None:
        if req.cover and req.cover not in (album.get("photos") or []):
            raise HTTPException(400, "Cover must be a photo in this album")
        repo.update_album_cover(album_id, req.cover or None)
        album["cover"] = req.cover or None

    album = repo.get_album(album_id)
    if not album:
        raise HTTPException(404, "Album not found")
    return {"ok": True, "album": {**album, "count": album["count"]}}
