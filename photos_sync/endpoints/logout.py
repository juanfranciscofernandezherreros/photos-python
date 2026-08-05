"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Request,
)

router = APIRouter()

@router.post("/api/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}
