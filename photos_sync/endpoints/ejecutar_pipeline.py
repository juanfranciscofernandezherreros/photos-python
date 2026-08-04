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

@router.post("/api/pipeline/ejecutar")
def ejecutar_pipeline(req: PipelineRequest, _auth: dict = Depends(require_admin)):
    try:
        names = pipeline.run(req.pasos)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"ok": True, "pasos": names}
