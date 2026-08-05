"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    _clear_failures,
    require_admin,
)

router = APIRouter()

@router.delete("/api/auth/lockouts/{username}")
def unlock_user(username: str, _admin: dict = Depends(require_admin)):
    """Admin can manually unlock a locked-out account."""
    _clear_failures(username)
    return {"ok": True}
