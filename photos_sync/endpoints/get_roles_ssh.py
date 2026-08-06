"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    require_admin,
    ssh_connection,
)

router = APIRouter()

@router.get("/api/ssh/roles")
def get_roles_ssh(_auth: dict = Depends(require_admin)):
    """Return valid legacy role values and their rendering rules."""
    return {
        "roles": ssh_connection.VALID_ROLES,
        "requiere_ruta_destino": ["destino", "ambos"],
        "ruta_destino_obligatoria": ["ambos"],
        "descripcion": {
            "origen":  "The pipeline scans this server for captures.",
            "destino": "Organized files are uploaded to this server.",
            "ambos":   "Source and destination; separate paths prevent loops.",
        },
    }
