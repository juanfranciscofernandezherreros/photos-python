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

@router.post("/api/users")
def create_user_endpoint(req: CreateUserIn, admin: dict = Depends(require_admin)):
    role = req.role if req.role in ("user", "admin") else "user"
    auth.validate_password_strength(req.password)
    try:
        user = repo.create_user(
            username=req.username,
            password_hash=auth.hash_password(req.password),
            role=role,
        )
    except repo.AdminExistsError:
        raise HTTPException(400, "An administrator already exists — only one is allowed")
    except repo.UsernameTakenError:
        raise HTTPException(400, "Username is already taken")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "user": user}
