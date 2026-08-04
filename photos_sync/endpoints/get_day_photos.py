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

@router.get("/api/days/{date}/photos")
def get_day_photos(
    date: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=24, ge=1, le=100),
    _auth: dict = Depends(require_login),
):
    """
    Return a paginated list of photos for a day.

    Accepted dates:
    - YYYY-MM-DD
    - undated
    """

    favourites: set[str] = repo.favourites_set()
    candidates: list[dict] = []

    for capture in repo.load_captures():
        file_path = (
            capture.get("ruta_destino")
            or capture.get("ruta_original")
            or ""
        )

        if not file_path:
            continue

        capture_date = str(capture.get("fecha_captura") or "").strip()
        photo_date = ""

        if len(capture_date) >= 10:
            photo_date = capture_date[:10]

        elif capture.get("mtime") is not None:
            try:
                photo_date = _dt.fromtimestamp(
                    float(capture["mtime"])
                ).strftime("%Y-%m-%d")
            except (TypeError, ValueError, OSError, OverflowError):
                photo_date = ""

        if not photo_date:
            photo_date = "undated"

        if photo_date != date:
            continue

        path = Path(file_path)

        # No se consulta todavía el disco.
        candidates.append({
            "id": file_path,
            "filename": path.name,
            "capture_date": capture_date,
            "tags": capture.get("tags") or [],
            "city": capture.get("city") or "",
            "gps_lat": capture.get("gps_lat"),
            "gps_lon": capture.get("gps_lon"),
            "favourite": file_path in favourites,
            "stored_size_mb": capture.get("tamano_mb") or 0,
        })

    candidates.sort(
        key=lambda photo: photo["filename"].casefold()
    )

    total = len(candidates)
    selected = candidates[offset:offset + limit]

    photos: list[dict] = []

    # El acceso al disco se limita a las fotos de esta página.
    for candidate in selected:
        file_path = candidate["id"]
        path = Path(file_path)

        try:
            stat_result = path.stat()
            exists = path.is_file()
            size_mb = (
                round(stat_result.st_size / 1_048_576, 2)
                if exists
                else candidate["stored_size_mb"]
            )
        except OSError:
            exists = False
            size_mb = candidate["stored_size_mb"]

        photos.append({
            "id": file_path,
            "filename": candidate["filename"],
            "size_mb": size_mb,
            "capture_date": candidate["capture_date"],
            "tags": candidate["tags"],
            "city": candidate["city"],
            "gps_lat": candidate["gps_lat"],
            "gps_lon": candidate["gps_lon"],
            "favourite": candidate["favourite"],
            "exists": exists,
            "url": (
                f"/api/photo?"
                f"path={quote(file_path, safe='')}"
            ),
        })

    next_offset = offset + len(photos)
    has_more = next_offset < total

    return {
        "date": date,
        "photos": photos,
        "count": total,
        "offset": offset,
        "limit": limit,
        "has_more": has_more,
        "next_offset": next_offset if has_more else None,
    }
