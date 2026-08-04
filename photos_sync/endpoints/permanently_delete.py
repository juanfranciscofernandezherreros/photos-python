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

@router.post("/api/trash/delete")
def permanently_delete(req: TrashActionIn, _auth: dict = Depends(require_login)):
    """Permanently delete trashed photos (cannot be undone)."""
    deleted, errors = 0, []
    for entry_id in req.ids:
        entry = repo.get_trash_entry(entry_id)
        if not entry:
            continue
        try:
            p = Path(entry["trash_path"])
            if p.is_file():
                p.unlink()
            repo.remove_trash_entry(entry_id)
            deleted += 1
        except Exception as e:
            errors.append(f"{entry['filename']}: {e}")
    return {"ok": True, "deleted": deleted, "errors": errors}
