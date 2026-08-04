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

@router.get("/api/photos/by-city/{city}")
def photos_by_city(city: str, _auth: dict = Depends(require_login)):
    """Return all photo paths that have the given city in their metadata."""
    photos = repo.photos_by_city(city)
    return {"city": city, "photos": photos, "count": len(photos)}
