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

@router.post("/api/webdav/connect")
async def connect_webdav(datos: ConnectionWebDAVIn, _auth: dict = Depends(require_admin)):
    loop = asyncio.get_event_loop()
    exito, mensaje = await loop.run_in_executor(
        _net_executor,
        lambda: connection.mount(datos.letra, datos.ip, datos.puerto),
    )
    if exito:
        connection.add_or_update_connection(
            datos.letra, datos.ip, datos.puerto, datos.alias or datos.letra
        )
    return {"ok": exito, "mensaje": mensaje}
