"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    require_admin,
    ssh_connection,
)

router = APIRouter()

@router.get("/api/ssh")
def listar_ssh(_auth: dict = Depends(require_admin)):
    connections = ssh_connection.load_ssh_connections()
    # Do not expose private-key paths in API responses.
    return [
        {k: v for k, v in c.items() if k != "clave_privada"}
        | {"tiene_clave": bool(c.get("clave_privada"))}
        for c in connections
    ]
