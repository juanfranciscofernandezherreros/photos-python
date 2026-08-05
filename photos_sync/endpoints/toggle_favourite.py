"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    FavouriteToggleIn,
    repo,
    require_login,
)

router = APIRouter()

@router.post("/api/favourites")
def toggle_favourite(req: FavouriteToggleIn, _auth: dict = Depends(require_login)):
    """Add or remove a photo from favourites."""
    # Ensure a captures row exists for this path
    if not repo.get_capture_by_dest(req.path):
        from pathlib import Path as _Path
        _f = _Path(req.path)
        repo.upsert_captures([{
            "id": req.path, "archivo": _f.name, "formato": _f.suffix.lstrip("."),
            "tamano_mb": round(_f.stat().st_size / 1048576, 2) if _f.is_file() else 0,
            "mtime": _f.stat().st_mtime if _f.is_file() else 0,
            "fecha_captura": "", "ruta_original": "",
            "ruta_destino": req.path, "tags": [],
        }])
    repo.set_favourite(req.path, req.favourite)
    return {"ok": True}
