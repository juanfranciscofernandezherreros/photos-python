"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    _login_failures,
    _time,
    require_admin,
)

router = APIRouter()

@router.get("/api/auth/lockouts")
def get_lockouts(_admin: dict = Depends(require_admin)):
    """Return all currently locked-out usernames and their unlock time."""
    now = _time.time()
    return {
        "lockouts": [
            {
                "username":       u,
                "failures":       s["failures"],
                "locked_until":   int(s["locked_until"]),
                "remaining_secs": max(0, int(s["locked_until"] - now)),
            }
            for u, s in _login_failures.items()
            if s["locked_until"] > now
        ]
    }
