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

@router.post("/api/carpetas/origen/quitar")
def quitar_carpeta(datos: QuitarCarpetaIn, _auth: dict = Depends(require_admin)):
    actuales = [c for c in load_saved_folders() if str(c) != datos.carpeta]
    save_folders(actuales)
    return {"ok": True, "origen": [str(c) for c in actuales]}
