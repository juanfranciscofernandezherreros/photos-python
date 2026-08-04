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

@router.get("/api/trash")
def get_trash(_auth: dict = Depends(require_login)):
    """List all photos currently in the trash."""
    from urllib.parse import quote
    entries = repo.list_trash()
    for e in entries:
        # thumbnail served from the trash location
        e["url"] = f"/api/photo?path={quote(e['trash_path'])}"
        e["exists"] = Path(e["trash_path"]).is_file()
    return {"trash": entries, "total": len(entries), "count": repo.trash_count()}
