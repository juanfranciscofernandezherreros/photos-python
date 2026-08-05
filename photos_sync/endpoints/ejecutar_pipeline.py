"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    HTTPException,
    PipelineRequest,
    pipeline,
    require_admin,
)

router = APIRouter()

@router.post("/api/pipeline/ejecutar")
def ejecutar_pipeline(req: PipelineRequest, _auth: dict = Depends(require_admin)):
    try:
        names = pipeline.run(req.pasos)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"ok": True, "pasos": names}
