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

@router.get("/api/cities")
def get_cities(_auth: dict = Depends(require_login)):
    """Return all distinct cities extracted from GPS EXIF metadata.
    Each entry: city name, photo count, cover photo path, coordinates."""
    cities = repo.load_all_cities()
    return {"cities": cities, "total": len(cities)}
