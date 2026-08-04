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

@router.get("/api/tags")
def get_tags(_auth: dict = Depends(require_login)):
    """Return all distinct tags across all captures with their counts."""
    tags = repo.load_all_tags()
    return {"tags": tags, "total_captures": len(tags)}
