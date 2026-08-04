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
