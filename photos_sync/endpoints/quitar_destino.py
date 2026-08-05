"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    load_destination_config,
    require_admin,
    save_destination,
)

router = APIRouter()

@router.post("/api/carpetas/destino/quitar")
def quitar_destino(_auth: dict = Depends(require_admin)):
    save_destination("")
    return {"ok": True, "destino": load_destination_config()}
