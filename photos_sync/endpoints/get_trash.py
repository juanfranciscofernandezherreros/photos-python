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
    import shutil
    from urllib.parse import quote

    entries = repo.list_trash()
    for e in entries:
        trash_path = Path(e["trash_path"])
        # Older builds could place shallow library paths in the container's
        # ephemeral /.trash directory. Migrate recoverable files on access.
        if trash_path.is_file() and trash_path.parent.resolve() == Path("/.trash").resolve():
            destination_dir = _trash_directory_for(Path(e["original_path"]))
            destination_dir.mkdir(parents=True, exist_ok=True)
            destination = destination_dir / trash_path.name
            if destination.exists():
                destination = destination_dir / f"{destination.stem}_{e['id']}{destination.suffix}"
            shutil.move(str(trash_path), str(destination))
            repo.update_trash_path(e["id"], str(destination))
            e["trash_path"] = str(destination)
            trash_path = destination
        # thumbnail served from the trash location
        e["url"] = f"/api/photo?path={quote(e['trash_path'])}"
        e["exists"] = trash_path.is_file()
    return {"trash": entries, "total": len(entries), "count": repo.trash_count()}
