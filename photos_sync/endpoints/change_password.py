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

@router.post("/api/auth/change-password")
def change_password(req: ChangePasswordIn, user: dict = Depends(require_login)):
    full = repo.get_user_by_username(user["username"])
    if not full or not auth.verify_password(req.current_password, full["password_hash"]):
        raise HTTPException(400, "Current password is incorrect")
    auth.validate_password_strength(req.new_password)
    repo.set_user_password(user["id"], auth.hash_password(req.new_password))
    return {"ok": True}
