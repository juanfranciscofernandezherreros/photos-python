"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    pipeline,
    require_admin,
)

router = APIRouter()

@router.get("/api/pipeline/estado")
def pipeline_estado(_auth: dict = Depends(require_admin)):
    return {"corriendo": pipeline.is_running()}
