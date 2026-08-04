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

@router.get("/api/pasos")
def get_pasos(_auth: dict = Depends(require_admin)):
    return [{"id": i, "nombre": n} for i, n in enumerate(pipeline.step_names())]
