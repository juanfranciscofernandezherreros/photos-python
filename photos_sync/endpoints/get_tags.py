"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    repo,
    require_login,
)

router = APIRouter()

@router.get("/api/tags")
def get_tags(_auth: dict = Depends(require_login)):
    """Return all distinct tags across all captures with their counts."""
    tags = repo.load_all_tags()
    return {"tags": tags, "total_captures": len(tags)}
