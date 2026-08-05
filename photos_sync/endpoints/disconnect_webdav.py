"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    _net_executor,
    asyncio,
    connection,
    require_admin,
)

router = APIRouter()

@router.post("/api/webdav/disconnect/{letra}")
async def disconnect_webdav(letra: str, _auth: dict = Depends(require_admin)):
    loop = asyncio.get_event_loop()
    exito, mensaje = await loop.run_in_executor(
        _net_executor,
        lambda: connection.unmount(letra),
    )
    if exito:
        connection.remove_connection(letra)
    return {"ok": exito, "mensaje": mensaje}
