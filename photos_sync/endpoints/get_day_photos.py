"""Endpoint implemented in its own router module."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query

from .. import repository as repo
from ..auth import require_login

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

    selected, total = repo.load_captures_for_day(date, offset, limit)

    photos: list[dict] = []

    # Limit disk access to captures selected by SQL.
    for candidate in selected:
        file_path = candidate["file_path"]
        path = Path(file_path)

        try:
            stat_result = path.stat()
            exists = path.is_file()
            size_mb = (
                round(stat_result.st_size / 1_048_576, 2)
                if exists
                else candidate.get("tamano_mb") or 0
            )
        except OSError:
            exists = False
            size_mb = candidate.get("tamano_mb") or 0

        photos.append({
            "id": file_path,
            "filename": candidate.get("archivo") or path.name,
            "size_mb": size_mb,
            "capture_date": candidate.get("fecha_captura") or "",
            "tags": candidate.get("tags") or [],
            "gps_lat": candidate.get("gps_lat"),
            "gps_lon": candidate.get("gps_lon"),
            "favourite": bool(candidate.get("is_favourite")),
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
