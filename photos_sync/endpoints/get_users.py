"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    repo,
    require_admin,
)

router = APIRouter()

@router.get("/api/users")
def get_users(admin: dict = Depends(require_admin)):
    return {"users": repo.list_users(), "total": repo.user_count()}
