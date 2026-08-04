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

@router.post("/api/auth/setup-admin")
@limiter.limit("5/minute")
def setup_admin(request: Request, req: AdminSetupIn):
    """Public — but only works once, while no admin exists yet."""
    if repo.admin_exists():
        raise HTTPException(403, "An administrator already exists")
    auth.validate_password_strength(req.password)
    try:
        user = repo.create_user(
            username=req.username,
            password_hash=auth.hash_password(req.password),
            role="admin",
        )
    except repo.AdminExistsError:
        raise HTTPException(403, "An administrator already exists")
    except repo.UsernameTakenError:
        raise HTTPException(400, "Username is already taken")
    except ValueError as e:
        raise HTTPException(400, str(e))
    # Auto-login the new admin
    request.session["user_id"] = user["id"]
    return {"ok": True, "user": user}
