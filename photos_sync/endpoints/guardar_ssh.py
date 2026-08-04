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
