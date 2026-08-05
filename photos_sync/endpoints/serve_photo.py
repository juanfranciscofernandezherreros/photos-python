"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    HTTPException,
    Path,
    _is_allowed,
    require_login,
)

router = APIRouter()

@router.get("/api/photo")
def serve_photo(path: str, _auth: dict = Depends(require_login)):
    """Serve a full-resolution photo file by its absolute path.
    Allows files inside ORGANIZED_DIR or the user-configured destination."""
    import mimetypes

    from fastapi.responses import FileResponse

    p = Path(path)
    if not _is_allowed(p):
        raise HTTPException(403, "Access denied — path not inside any configured destination")
    if not p.is_file():
        raise HTTPException(404, "File not found")
    mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    return FileResponse(p, media_type=mime)
