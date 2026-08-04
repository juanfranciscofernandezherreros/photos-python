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

@router.get("/api/auth/status")
def auth_status(request: Request):
    """Public. Tells the frontend which screen to show."""
    user = auth.current_user(request)
    return {
        "admin_exists": repo.admin_exists(),
        "authenticated": user is not None,
        "user": {"id": user["id"], "username": user["username"], "role": user["role"]}
                 if user else None,
    }
