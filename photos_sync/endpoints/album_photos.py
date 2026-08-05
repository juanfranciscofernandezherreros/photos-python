"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    AlbumPhotosIn,
    Depends,
    HTTPException,
    Path,
    _is_allowed,
    repo,
    require_login,
)

router = APIRouter()

@router.post("/api/albums/{album_id}/photos")
def album_photos(album_id: str, req: AlbumPhotosIn, _auth: dict = Depends(require_login)):
    """Add or remove photos in an album by path. action: 'add' | 'remove'."""
    if req.action not in ("add", "remove"):
        raise HTTPException(400, f"Unknown action: {req.action!r}")

    if not repo.get_album(album_id):
        raise HTTPException(404, "Album not found")

    if req.action == "add":
        allowed = [p for p in req.paths if _is_allowed(Path(p))]
        count = repo.album_add_photos(album_id, allowed)
    else:
        count = repo.album_remove_photos(album_id, req.paths)

    return {"ok": True, "count": count}
