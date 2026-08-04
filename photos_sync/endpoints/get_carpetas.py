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

@router.get("/api/carpetas")
def get_carpetas(_auth: dict = Depends(require_admin)):
    """Estado completo de carpetas: origen + destino + servidores SSH
    disponibles como destino. La UI renderiza todo a partir de esto,
    sin estado propio en JS."""
    return {
        "origen": [str(c) for c in load_saved_folders()],
        "destino": load_destination_config(),
        "servidores_ssh_destino": [
            {"alias": c["alias"], "host": c["host"]}
            for c in ssh_connection.load_ssh_connections()
            if c["rol"] in ("destino", "ambos")
        ],
    }
