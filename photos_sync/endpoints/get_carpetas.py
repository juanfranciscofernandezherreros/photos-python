"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    load_destination_config,
    load_saved_folders,
    require_admin,
    ssh_connection,
)

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
