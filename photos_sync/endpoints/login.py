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

@router.post("/api/auth/login")
@limiter.limit("10/minute")
def login(request: Request, req: LoginIn):
    """5 attempts per minute per IP. 10 consecutive failures locks the account
    for 15 minutes (in-memory, resets on server restart)."""
    _check_lockout(req.username)
    user = repo.get_user_by_username((req.username or "").strip())
    if not user or not user.get("active", True) or \
       not auth.verify_password(req.password, user["password_hash"]):
        _record_failure(req.username)
        raise HTTPException(401, "Invalid username or password")
    _clear_failures(req.username)
    request.session["user_id"] = user["id"]
    return {"ok": True, "user": {"id": user["id"], "username": user["username"],
                                  "role": user["role"]}}
