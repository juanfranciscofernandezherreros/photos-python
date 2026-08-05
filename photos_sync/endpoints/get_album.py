"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    HTTPException,
    Path,
    repo,
    require_login,
)

router = APIRouter()

@router.get("/api/albums/{album_id}")
def get_album(album_id: str, _auth: dict = Depends(require_login)):
    """Return the photos in an album, in the same shape as day photos."""
    album = repo.get_album(album_id)
    if album is None:
        raise HTTPException(404, "Album not found")

    from urllib.parse import quote
    favs = repo.favourites_set()
    meta_by_dest = {m.get("ruta_destino"): m for m in repo.load_captures() if m.get("ruta_destino")}

    photos = []
    for fpath in (album.get("photos") or []):
        path_obj = Path(fpath)
        exists = path_obj.is_file()
        meta = meta_by_dest.get(fpath, {})
        photos.append({
            "id":           fpath,
            "filename":     path_obj.name,
            "size_mb":      round(path_obj.stat().st_size / 1048576, 2) if exists else 0,
            "capture_date": meta.get("fecha_captura", ""),
            "tags":         meta.get("tags", []),
            "gps_lat":      meta.get("gps_lat"),
            "gps_lon":      meta.get("gps_lon"),
            "favourite":    fpath in favs,
            "exists":       exists,
            "url":          f"/api/photo?path={quote(fpath)}",
        })
    return {
        "id":      album["id"],
        "name":    album.get("name", "Untitled"),
        "created": album.get("created", ""),
        "count":   len(photos),
        "photos":  photos,
    }
