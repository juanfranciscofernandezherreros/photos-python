"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    pipeline,
    require_admin,
)

router = APIRouter()

@router.get("/api/pasos")
def get_pasos(_auth: dict = Depends(require_admin)):
    return [{"id": i, "nombre": n} for i, n in enumerate(pipeline.step_names())]
