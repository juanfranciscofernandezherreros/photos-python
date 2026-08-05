"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    BulkActionIn,
    Depends,
    HTTPException,
    Path,
    _is_allowed,
    _trash_directory_for,
    repo,
    require_login,
)

router = APIRouter()

@router.post("/api/photos/bulk")
def bulk_action(req: BulkActionIn, _auth: dict = Depends(require_login)):
    """Perform a bulk action on a list of photo paths.
    action: 'favourite' | 'unfavourite' | 'delete'
    delete: moves files to a .trash/ subfolder next to the photo."""
    import shutil

    if req.action not in ("favourite", "unfavourite", "delete"):
        raise HTTPException(400, f"Unknown action: {req.action!r}")

    ok_paths = [p for p in req.paths if _is_allowed(Path(p))]
    if not ok_paths:
        raise HTTPException(403, "No allowed paths in request")

    if req.action in ("favourite", "unfavourite"):
        flag = req.action == "favourite"
        # Ensure every path exists as a capture row (upsert minimal record)
        from pathlib import Path as _Path
        for p in ok_paths:
            if not repo.get_capture_by_dest(p):
                _f = _Path(p)
                repo.upsert_captures([{
                    "id": p, "archivo": _f.name, "formato": _f.suffix.lstrip("."),
                    "tamano_mb": round(_f.stat().st_size / 1048576, 2) if _f.is_file() else 0,
                    "mtime": _f.stat().st_mtime if _f.is_file() else 0,
                    "fecha_captura": "", "ruta_original": "",
                    "ruta_destino": p, "tags": [],
                }])
        count = repo.bulk_set_favourite(ok_paths, flag)
        total = len(repo.load_favourites())
        return {"ok": True, "affected": count, "total_favourites": total, "moved": 0}

    # delete → move to .trash/ and record for restore
    moved, errors = 0, []
    for path_str in ok_paths:
        src = Path(path_str)
        if not src.is_file():
            continue
        trash = _trash_directory_for(src)
        trash.mkdir(parents=True, exist_ok=True)
        dest = trash / src.name
        # Avoid name collisions in trash
        if dest.exists():
            stem, suffix = src.stem, src.suffix
            dest = trash / f"{stem}_{src.stat().st_ino}{suffix}"
        try:
            size_mb = round(src.stat().st_size / 1048576, 2)
            shutil.move(str(src), str(dest))
            # Record so it can be restored later
            repo.add_to_trash(
                original_path=str(src),
                trash_path=str(dest),
                filename=src.name,
                size_mb=size_mb,
            )
            # Remove favourite flag / capture stays but dest_path now invalid
            moved += 1
        except Exception as e:
            errors.append(str(e))
    return {"ok": True, "moved": moved, "errors": errors}
