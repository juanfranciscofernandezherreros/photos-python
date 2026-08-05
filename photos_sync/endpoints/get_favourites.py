"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    repo,
    require_login,
)

router = APIRouter()

@router.get("/api/favourites")
def get_favourites(_auth: dict = Depends(require_login)):
    return {"favourites": repo.load_favourites()}
