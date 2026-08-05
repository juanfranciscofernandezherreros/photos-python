"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    connection,
    require_admin,
)

router = APIRouter()

@router.get("/api/webdav/letras")
def letras_disponibles(_auth: dict = Depends(require_admin)):
    """Letras de unidad disponibles (D:-Z:). El JS las usa para el <select>,
    sin hardcodear el rango en el cliente."""
    usadas = {c["letra"] for c in connection.load_connections()}
    return {
        "todas": connection.AVAILABLE_DRIVE_LETTERS,
        "libres": [d for d in connection.AVAILABLE_DRIVE_LETTERS if d not in usadas],
    }
