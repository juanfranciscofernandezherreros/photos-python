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

@router.post("/api/trash/empty")
def empty_trash(_auth: dict = Depends(require_login)):
    """Permanently delete everything in the trash."""
    entries = repo.list_trash()
    deleted = 0
    for e in entries:
        try:
            p = Path(e["trash_path"])
            if p.is_file():
                p.unlink()
            repo.remove_trash_entry(e["id"])
            deleted += 1
        except Exception:
            pass
    return {"ok": True, "deleted": deleted}
