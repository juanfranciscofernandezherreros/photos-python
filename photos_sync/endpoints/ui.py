"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    _HTML,
    HTMLResponse,
)

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
def ui():
    return _HTML
