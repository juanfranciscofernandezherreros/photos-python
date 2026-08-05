"""Endpoint implemented in its own router module."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from ..web_server import (
    Depends,
    QuitarCarpetaIn,
    load_saved_folders,
    require_admin,
    save_folders,
)

router = APIRouter()

@router.post("/api/carpetas/origen/quitar")
def quitar_carpeta(datos: QuitarCarpetaIn, _auth: dict = Depends(require_admin)):
    target = Path(datos.carpeta)
    actuales = [c for c in load_saved_folders() if c != target]
    save_folders(actuales)
    return {"ok": True, "origen": [str(c) for c in actuales]}
