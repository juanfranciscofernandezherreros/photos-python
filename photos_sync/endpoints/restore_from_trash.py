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

@router.post("/api/trash/restore")
def restore_from_trash(req: TrashActionIn, _auth: dict = Depends(require_login)):
    """Restore trashed photos to their original location."""
    import shutil
    restored, errors = 0, []
    for entry_id in req.ids:
        entry = repo.get_trash_entry(entry_id)
        if not entry:
            continue
        src = Path(entry["trash_path"])
        dest = Path(entry["original_path"])
        if not src.is_file():
            # File already gone — clean up the stale record
            repo.remove_trash_entry(entry_id)
            errors.append(f"{entry['filename']}: file missing from trash")
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            # If something now occupies the original path, restore alongside it
            if dest.exists():
                stem, suffix = dest.stem, dest.suffix
                dest = dest.parent / f"{stem}_restored{suffix}"
            shutil.move(str(src), str(dest))
            repo.remove_trash_entry(entry_id)
            restored += 1
        except Exception as e:
            errors.append(f"{entry['filename']}: {e}")
    return {"ok": True, "restored": restored, "errors": errors}
