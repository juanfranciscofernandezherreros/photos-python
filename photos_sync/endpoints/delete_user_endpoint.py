"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    HTTPException,
    repo,
    require_admin,
)

router = APIRouter()

@router.delete("/api/users/{user_id}")
def delete_user_endpoint(user_id: str, admin: dict = Depends(require_admin)):
    target = repo.get_user(user_id)
    if not target:
        raise HTTPException(404, "User not found")
    # The sole admin cannot be deleted (would lock everyone out of config)
    if target["role"] == "admin" and repo.count_admins() <= 1:
        raise HTTPException(400, "Cannot delete the only administrator")
    if user_id == admin["id"]:
        raise HTTPException(400, "You cannot delete your own account")
    repo.delete_user(user_id)
    return {"ok": True}
