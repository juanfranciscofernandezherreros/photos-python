"""Searchable per-photo EXIF metadata endpoints."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import repository as repo
from ..auth import require_login

router = APIRouter()


def _with_urls(item: dict) -> dict:
    path = item.get("file_path") or ""
    encoded = quote(path, safe="")
    return {
        **item,
        "photo_url": f"/api/photo?path={encoded}" if path else None,
        "thumbnail_url": f"/api/thumb?path={encoded}" if path else None,
    }


@router.get("/api/exif")
def get_exif_page(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    query: str = Query(default="", max_length=200),
    status: str = Query(
        default="all",
        pattern="^(all|with_exif|without_exif|errors|pending)$",
    ),
    _auth: dict = Depends(require_login),
):
    """Return searchable normalized EXIF rows and extraction coverage."""
    records, total, stats = repo.load_photo_exif_page(offset, limit, query, status)
    next_offset = offset + len(records)
    return {
        "records": [_with_urls(record) for record in records],
        "count": total,
        "offset": offset,
        "limit": limit,
        "has_more": next_offset < total,
        "next_offset": next_offset if next_offset < total else None,
        "stats": stats,
    }


@router.get("/api/exif/{capture_id}")
def get_exif_detail(
    capture_id: str,
    _auth: dict = Depends(require_login),
):
    """Return all stored EXIF fields, including safe vendor-specific tags."""
    record = repo.get_photo_exif(capture_id)
    if record is None:
        raise HTTPException(404, "Photo not found")
    return _with_urls(record)
