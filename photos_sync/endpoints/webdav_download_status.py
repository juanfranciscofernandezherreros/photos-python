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

@router.get("/api/webdav/download-status")
def webdav_download_status(_auth: dict = Depends(require_admin)):
    """Poll this to know how the background download is going."""
    return dict(_webdav_job)
