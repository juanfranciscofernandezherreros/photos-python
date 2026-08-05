"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    require_admin,
    ssh_connection,
)

router = APIRouter()

@router.delete("/api/ssh/{alias}")
def eliminar_ssh(alias: str, _auth: dict = Depends(require_admin)):
    ssh_connection.remove_ssh_connection(alias)
    return {"ok": True}
