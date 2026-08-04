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

@router.post("/api/carpetas/destino")
def set_destino(datos: DestinoIn, _auth: dict = Depends(require_admin)):
    if datos.tipo == "local":
        if not datos.ruta:
            raise HTTPException(400, "Falta la ruta para destino local.")
        save_destination(datos.ruta)
    elif datos.tipo == "ssh":
        if not datos.alias:
            raise HTTPException(400, "Falta el alias del servidor SSH.")
        c = ssh_connection.get_connection(datos.alias)
        if c is None:
            raise HTTPException(404, f"No existe ninguna conexión SSH con alias '{datos.alias}'.")
        if c["rol"] not in ("destino", "ambos"):
            raise HTTPException(400,
                f"El servidor '{datos.alias}' tiene rol '{c['rol']}': "
                "para usarlo como destino debe tener rol 'destino' o 'ambos'.")
        save_ssh_destination(datos.alias)
    else:
        raise HTTPException(400, "tipo debe ser 'local' o 'ssh'.")
    return {"ok": True, "destino": load_destination_config()}
