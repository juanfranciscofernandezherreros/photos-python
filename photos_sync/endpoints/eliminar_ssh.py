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

@router.delete("/api/ssh/{alias}")
def eliminar_ssh(alias: str, _auth: dict = Depends(require_admin)):
    ssh_connection.remove_ssh_connection(alias)
    return {"ok": True}
