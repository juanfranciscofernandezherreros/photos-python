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

@router.get("/api/users")
def get_users(admin: dict = Depends(require_admin)):
    return {"users": repo.list_users(), "total": repo.user_count()}
