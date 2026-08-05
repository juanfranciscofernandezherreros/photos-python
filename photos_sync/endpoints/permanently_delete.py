"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    Path,
    TrashActionIn,
    repo,
    require_login,
)

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
