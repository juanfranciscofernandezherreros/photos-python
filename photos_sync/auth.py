"""
auth.py — Password hashing + FastAPI auth dependencies.

Passwords are hashed with bcrypt (via passlib). Sessions are cookie-based
(Starlette SessionMiddleware); this module reads request.session to
identify the current user and provides dependencies to gate endpoints.
"""
from __future__ import annotations

# ── Password hashing ──────────────────────────────────────────────────────────
# We use the bcrypt library directly (not passlib) because passlib's
# version-detection breaks with bcrypt >= 4.x. bcrypt has a 72-byte input
# limit, so we pre-hash long passwords with SHA-256 before bcrypt.
import hashlib

from fastapi import HTTPException, Request

from . import repository as repo

try:
    import bcrypt as _bcrypt
    _BCRYPT_OK = True
except ImportError:  # pragma: no cover
    _BCRYPT_OK = False

MIN_PASSWORD_LEN = 8


def _prepare(plain: str) -> bytes:
    """SHA-256 the password first so bcrypt's 72-byte limit never bites,
    and return the digest as bytes bcrypt can consume."""
    return hashlib.sha256(plain.encode("utf-8")).digest()


def hash_password(plain: str) -> str:
    if _BCRYPT_OK:
        # base64 the sha256 digest to keep it in the bcrypt byte budget
        import base64
        pre = base64.b64encode(_prepare(plain))
        return _bcrypt.hashpw(pre, _bcrypt.gensalt()).decode("utf-8")
    # Fallback (should not happen in prod): salted sha256
    import os
    salt = os.urandom(16).hex()
    h = hashlib.sha256((salt + plain).encode()).hexdigest()
    return f"sha256${salt}${h}"


def verify_password(plain: str, hashed: str) -> bool:
    if hashed.startswith("sha256$"):
        _, salt, h = hashed.split("$", 2)
        return hashlib.sha256((salt + plain).encode()).hexdigest() == h
    if _BCRYPT_OK:
        try:
            import base64
            pre = base64.b64encode(_prepare(plain))
            return _bcrypt.checkpw(pre, hashed.encode("utf-8"))
        except Exception:
            return False
    return False


def validate_password_strength(plain: str) -> None:
    if len(plain or "") < MIN_PASSWORD_LEN:
        raise HTTPException(
            400, f"Password must be at least {MIN_PASSWORD_LEN} characters"
        )


# ── Current-user helpers / dependencies ───────────────────────────────────────

def current_user(request: Request) -> dict | None:
    """Return the logged-in user dict, or None if not authenticated."""
    uid = request.session.get("user_id")
    if not uid:
        return None
    user = repo.get_user(uid)
    if not user or not user.get("active", True):
        return None
    return user


def require_login(request: Request) -> dict:
    """FastAPI dependency: 401 if not logged in."""
    user = current_user(request)
    if user is None:
        raise HTTPException(401, "Authentication required")
    return user


def require_admin(request: Request) -> dict:
    """FastAPI dependency: 401 if not logged in, 403 if not admin."""
    user = require_login(request)
    if user.get("role") != "admin":
        raise HTTPException(403, "Administrator privileges required")
    return user
