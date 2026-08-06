"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    DestinoIn,
    HTTPException,
    load_destination_config,
    require_admin,
    save_destination,
    save_ssh_destination,
    ssh_connection,
)

router = APIRouter()

@router.post("/api/carpetas/destino")
def set_destino(datos: DestinoIn, _auth: dict = Depends(require_admin)):
    if datos.tipo == "local":
        if not datos.ruta:
            raise HTTPException(400, "A local destination path is required.")
        save_destination(datos.ruta)
    elif datos.tipo == "ssh":
        if not datos.alias:
            raise HTTPException(400, "An SSH server alias is required.")
        c = ssh_connection.get_connection(datos.alias)
        if c is None:
            raise HTTPException(404, f"No SSH connection has alias '{datos.alias}'.")
        if c["rol"] not in ("destino", "ambos"):
            raise HTTPException(400,
                f"Server '{datos.alias}' has role '{c['rol']}'; "
                "a destination requires the legacy role 'destino' or 'ambos'.")
        save_ssh_destination(datos.alias)
    else:
        raise HTTPException(400, "tipo must be 'local' or 'ssh'.")
    return {"ok": True, "destino": load_destination_config()}
