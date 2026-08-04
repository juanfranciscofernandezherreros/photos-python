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

@router.post("/api/trash/purge-old")
def purge_old_trash(days: int = 30, _admin: dict = Depends(require_admin)):
    """Permanently delete trash entries older than `days` days.
    Intended to be called periodically; admin-only."""
    old = repo.trash_entries_older_than(days)
    purged = 0
    for e in old:
        try:
            p = Path(e["trash_path"])
            if p.is_file():
                p.unlink()
            repo.remove_trash_entry(e["id"])
            purged += 1
        except Exception:
            pass
    return {"ok": True, "purged": purged, "days": days}
