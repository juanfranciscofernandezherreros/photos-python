"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    connection,
    require_admin,
)

router = APIRouter()

@router.get("/api/webdav")
def listar_webdav(_auth: dict = Depends(require_admin)):
    return [
        {**c, "montada": connection.is_mounted(c["letra"])}
        for c in connection.load_connections()
    ]
