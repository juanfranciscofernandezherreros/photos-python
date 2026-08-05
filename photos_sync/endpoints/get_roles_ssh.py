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
    """Devuelve los roles válidos y sus reglas, para que la UI los renderice
    sin hardcodear ninguna regla en JS."""
    return {
        "roles": ssh_connection.VALID_ROLES,
        "requiere_ruta_destino": ["destino", "ambos"],
        "ruta_destino_obligatoria": ["ambos"],
        "descripcion": {
            "origen":  "El pipeline escanea este servidor en busca de capturas.",
            "destino": "Lo organizado se sube a este servidor.",
            "ambos":   "Origen Y destino. Requiere rutas distintas para evitar bucles.",
        },
    }
