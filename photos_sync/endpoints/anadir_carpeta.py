"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    AnadirCarpetaIn,
    Depends,
    HTTPException,
    Path,
    load_saved_folders,
    require_admin,
    save_folders,
)

router = APIRouter()

@router.post("/api/carpetas/origen/anadir")
def anadir_carpeta(datos: AnadirCarpetaIn, _auth: dict = Depends(require_admin)):
    carpeta = datos.carpeta.strip()
    if not carpeta:
        raise HTTPException(400, "Folder cannot be empty.")
    actuales = load_saved_folders()
    if Path(carpeta) not in actuales:
        actuales.append(Path(carpeta))
        save_folders(actuales)
    return {"ok": True, "origen": [str(c) for c in actuales]}
