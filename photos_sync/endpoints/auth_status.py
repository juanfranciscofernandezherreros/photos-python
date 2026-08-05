"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Request,
    auth,
    repo,
)

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
