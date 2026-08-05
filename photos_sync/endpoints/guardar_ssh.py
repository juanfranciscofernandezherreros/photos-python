"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    HTTPException,
    SSHConnectionIn,
    require_admin,
    ssh_connection,
)

router = APIRouter()

@router.post("/api/ssh")
def guardar_ssh(datos: SSHConnectionIn, _auth: dict = Depends(require_admin)):
    # Si el cliente envía clave_privada vacía, preservar la que ya existía
    clave = datos.clave_privada
    if not clave:
        existentes = ssh_connection.load_ssh_connections()
        prev = next((c for c in existentes if c["alias"] == datos.alias), None)
        if prev:
            clave = prev.get("clave_privada", "")
    try:
        ssh_connection.add_or_update_ssh_connection(
            alias=datos.alias, host=datos.host, puerto=datos.puerto,
            usuario=datos.usuario, ruta_remota=datos.ruta_remota,
            clave_privada=clave, rol=datos.rol,
            ruta_remota_destino=datos.ruta_remota_destino,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}
