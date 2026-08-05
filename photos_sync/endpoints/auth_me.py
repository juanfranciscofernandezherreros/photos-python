"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    require_login,
)

router = APIRouter()

@router.get("/api/auth/me")
def auth_me(user: dict = Depends(require_login)):
    return {"user": user}
